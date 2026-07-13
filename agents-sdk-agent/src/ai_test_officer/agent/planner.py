from __future__ import annotations

import contextlib
import json
import signal
import threading
from dataclasses import dataclass
from typing import Iterator

from ..config import ALLOWED_FEATURE_ENV_ID, ALLOWED_FEATURE_ENV_NAME, DEFAULT_AGENT_PLANNER_TIMEOUT_SEC
from ..events import EventSink
from ..execution.planner import plan_test_commands
from ..models import AgentTurn, RunRecord, SafetyCheck
from ..prompts import load_prompt
from ..tools import AgentRunTools
from ..tools.safety import SafetyError, validate_temp_write_path, validate_test_command
from .config import configure_agents_sdk, model_provider_from_env

try:
    from agents import RunHooks
except ImportError:
    RunHooks = object  # type: ignore[assignment,misc]


class AgentPlannerUnavailable(RuntimeError):
    """Raised when Agent Planner is required but cannot be initialized."""


@dataclass(frozen=True)
class AgentPlannerResult:
    final_output: str
    used_model: bool


class _LiveRunHooks(RunHooks):
    """Emits ``tool_call`` start/end events around each Agents SDK tool invocation."""

    def __init__(self, sink: EventSink | None) -> None:
        self._sink = sink
        self._stack: list[str] = []
        self._lock = threading.Lock()
        self._counter = 0

    def _next_id(self) -> str:
        with self._lock:
            self._counter += 1
            return f"t{self._counter}"

    async def on_tool_start(self, context, agent, tool) -> None:
        tid = self._next_id()
        self._stack.append(tid)
        if self._sink is not None:
            self._sink.tool_call(tid, getattr(tool, "name", "tool"), "start")

    async def on_tool_end(self, context, agent, tool, result) -> None:
        tid = self._stack.pop() if self._stack else self._next_id()
        output = _summarize_output(str(result)) if result is not None else ""
        if self._sink is not None:
            self._sink.tool_call(tid, getattr(tool, "name", "tool"), "ok", output=output)


def run_agent_planner(
    record: RunRecord,
    tools: AgentRunTools,
    *,
    fallback_to_deterministic: bool,
    max_turns: int,
    sink: EventSink | None = None,
) -> AgentPlannerResult:
    provider = model_provider_from_env()
    if not provider.available:
        raise AgentPlannerUnavailable("missing model key: set ARK_API_KEY or OPENAI_API_KEY in .env")

    try:
        from agents import Agent, Runner, function_tool
    except ImportError as exc:
        raise AgentPlannerUnavailable("openai-agents is not installed") from exc
    try:
        from agents import ToolGuardrailFunctionOutput, tool_input_guardrail

        sdk_tool_guardrails_available = True
    except ImportError:
        ToolGuardrailFunctionOutput = None  # type: ignore[assignment]
        tool_input_guardrail = None  # type: ignore[assignment]
        sdk_tool_guardrails_available = False

    if not configure_agents_sdk(provider):
        raise AgentPlannerUnavailable("failed to configure Agents SDK model provider")

    def trace(name: str, input_summary: str, output: str) -> None:
        record.tools_used.append(name)
        record.planner_trace.append(f"tool:{name}")
        if sink is not None:
            sink.planner(f"tool:{name}")
        record.agent_turns.append(
            AgentTurn(
                turn=len(record.agent_turns) + 1,
                tool=name.split(":", 1)[0],
                input_summary=input_summary[:400],
                output_summary=_summarize_output(output),
                model_initiated=True,
            )
        )

    safe_test_command = None
    safe_temp_test_write = None
    if sdk_tool_guardrails_available and tool_input_guardrail is not None and ToolGuardrailFunctionOutput is not None:

        @tool_input_guardrail(name="safe_test_command")
        def safe_test_command(data):
            arguments = json.loads(data.context.tool_arguments or "{}")
            command = str(arguments.get("command", ""))
            try:
                validate_test_command(command)
            except SafetyError as exc:
                record.safety_checks.append(
                    SafetyCheck(
                        name="run_test_command",
                        action="execute",
                        target=command,
                        status="blocked",
                        blocked_by="tool_guardrail",
                        reason=str(exc),
                    )
                )
                return ToolGuardrailFunctionOutput.reject_content(str(exc), output_info={"command": command})
            return ToolGuardrailFunctionOutput.allow({"command": command})

        @tool_input_guardrail(name="safe_temp_test_write")
        def safe_temp_test_write(data):
            arguments = json.loads(data.context.tool_arguments or "{}")
            path = str(arguments.get("path", ""))
            try:
                validate_temp_write_path(record.workspace_repo, path, record.allow_temp_test_code)
            except SafetyError as exc:
                record.safety_checks.append(
                    SafetyCheck(
                        name="write_temp_test",
                        action="write",
                        target=path,
                        status="blocked",
                        blocked_by="tool_guardrail",
                        reason=str(exc),
                    )
                )
                return ToolGuardrailFunctionOutput.reject_content(str(exc), output_info={"path": path})
            return ToolGuardrailFunctionOutput.allow({"path": path})

    @function_tool(strict_mode=False)
    def list_changed_files() -> str:
        """List changed files for this MR or local git range."""
        output = tools.list_changed_files()
        trace("list_changed_files", "changed file list", output)
        return output

    @function_tool(strict_mode=False)
    def read_file_diff(path: str) -> str:
        """Read the indexed diff for one changed file path."""
        output = tools.read_file_diff(path)
        trace(f"read_file_diff:{path}", path, output)
        return output

    @function_tool(strict_mode=False)
    def read_file(path: str, start_line: int = 1, end_line: int = 200) -> str:
        """Read a bounded line range from the isolated workspace repo."""
        output = tools.read_file(path, start_line, end_line)
        trace(f"read_file:{path}:{start_line}-{end_line}", f"{path}:{start_line}-{end_line}", output)
        return output

    @function_tool(strict_mode=False)
    def search_repo(query: str) -> str:
        """Search the isolated workspace repo with ripgrep."""
        output = tools.search_repo(query)
        trace(f"search_repo:{query}", query, output)
        return output

    @function_tool(strict_mode=False)
    def get_package_scripts(package_json_path: str) -> str:
        """Read scripts from a package.json file in the isolated workspace repo."""
        output = tools.get_package_scripts(package_json_path)
        trace(f"get_package_scripts:{package_json_path}", package_json_path, output)
        return output

    run_test_command_tool_kwargs = (
        {"tool_input_guardrails": [safe_test_command]} if safe_test_command is not None else {}
    )
    write_temp_test_tool_kwargs = (
        {"tool_input_guardrails": [safe_temp_test_write]} if safe_temp_test_write is not None else {}
    )
    unread_failure_logs: set[int] = set()

    @function_tool(strict_mode=False, **run_test_command_tool_kwargs)
    def run_test_command(command: str) -> str:
        """Run a whitelisted test command in the isolated workspace repo."""
        if unread_failure_logs:
            command_id = min(unread_failure_logs)
            return json.dumps(
                {
                    "command": command,
                    "error": "read the previous failed command log before running another test",
                    "next_required_tool": f"read_test_log({command_id})",
                },
                ensure_ascii=False,
            )
        cid = f"c{len(record.commands) + 1}"
        if sink is not None:
            sink.command(cid, command, "start", category="agent")
        try:
            result = tools.run_test_command(command)
        except SafetyError as exc:
            record.safety_checks.append(
                SafetyCheck(
                    name="run_test_command",
                    action="execute",
                    target=command,
                    status="blocked",
                    blocked_by="local_safety_policy",
                    reason=str(exc),
                )
            )
            record.planner_trace.append(f"tool-error:run_test_command:{exc}")
            if sink is not None:
                sink.command(cid, command, "blocked", category="agent")
            output = json.dumps({"command": command, "error": str(exc)}, ensure_ascii=False)
            trace(f"run_test_command:{command}", command, output)
            return output
        except Exception as exc:
            record.planner_trace.append(f"tool-error:run_test_command:{exc}")
            if sink is not None:
                sink.command(cid, command, "fail", category="agent", returncode=-1)
            output = json.dumps({"command": command, "error": str(exc)}, ensure_ascii=False)
            trace(f"run_test_command:{command}", command, output)
            return output
        output = json.dumps(
            {
                "command": result.command,
                "returncode": result.returncode,
                "command_id": len(record.commands),
                "next_required_tool": f"read_test_log({len(record.commands)})" if result.returncode != 0 else None,
                "stdout_tail": result.stdout[-2000:],
                "stderr_tail": result.stderr[-2000:],
                "log_path": str(result.log_path.relative_to(record.run_dir)),
            },
            ensure_ascii=False,
        )
        if result.returncode != 0:
            unread_failure_logs.add(len(record.commands))
        if sink is not None:
            sink.command(
                cid,
                command,
                "ok" if result.returncode == 0 else "fail",
                category="agent",
                returncode=result.returncode,
                log_path=str(result.log_path.relative_to(record.run_dir)),
            )
        trace(f"run_test_command:{command}", command, output)
        return output

    @function_tool(strict_mode=False)
    def read_test_log(command_id: int) -> str:
        """Read a captured command log by 1-based command id."""
        try:
            output = tools.read_test_log(command_id)
        except Exception as exc:
            record.planner_trace.append(f"tool-error:read_test_log:{exc}")
            output = f"error: {exc}"
        else:
            unread_failure_logs.discard(command_id)
        trace(f"read_test_log:{command_id}", str(command_id), output)
        return output

    @function_tool(strict_mode=False, **write_temp_test_tool_kwargs)
    def write_temp_test(path: str, content: str, reason: str = "Agent generated temporary test.") -> str:
        """Write temporary test code inside allowed test/evidence paths only."""
        try:
            generated = tools.write_temp_test(path, content, reason)
        except SafetyError as exc:
            record.safety_checks.append(
                SafetyCheck(
                    name="write_temp_test",
                    action="write",
                    target=path,
                    status="blocked",
                    blocked_by="local_safety_policy",
                    reason=str(exc),
                )
            )
            record.planner_trace.append(f"tool-error:write_temp_test:{exc}")
            output = f"error: {exc}"
            trace(f"write_temp_test:{path}", f"{path}: {reason}", output)
            return output
        except Exception as exc:
            record.planner_trace.append(f"tool-error:write_temp_test:{exc}")
            output = f"error: {exc}"
            trace(f"write_temp_test:{path}", f"{path}: {reason}", output)
            return output
        output = str(generated.path.relative_to(record.run_dir))
        trace(f"write_temp_test:{path}", f"{path}: {reason}", output)
        return output

    agent = Agent(
        name="AI Test Officer Planner",
        instructions=load_prompt("test_officer"),
        model=provider.model,
        tools=[
            list_changed_files,
            read_file_diff,
            read_file,
            search_repo,
            get_package_scripts,
            run_test_command,
            read_test_log,
            write_temp_test,
        ],
    )
    prompt = _planner_prompt(record)
    try:
        with _planner_timeout(DEFAULT_AGENT_PLANNER_TIMEOUT_SEC):
            result = Runner.run_sync(agent, prompt, max_turns=max_turns, hooks=_LiveRunHooks(sink))
        final_output = str(getattr(result, "final_output", result))
        record.planner_trace.append("agent:completed")
        if sink is not None:
            sink.planner("agent:completed")
    except Exception as exc:
        final_output = f"Agent planner stopped before completion: {exc}"
        record.planner_trace.append(f"agent:error:{exc}")
        if sink is not None:
            sink.planner(f"agent:error:{exc}")
    if fallback_to_deterministic:
        _run_missing_deterministic_commands(record, tools, sink=sink)
    return AgentPlannerResult(final_output=final_output, used_model=True)


@contextlib.contextmanager
def _planner_timeout(seconds: int) -> Iterator[None]:
    if not hasattr(signal, "SIGALRM"):
        yield
        return
    previous_handler = signal.getsignal(signal.SIGALRM)

    def handle_timeout(signum, frame):
        raise TimeoutError(f"Agent planner timed out after {seconds}s")

    signal.signal(signal.SIGALRM, handle_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _planner_prompt(record: RunRecord) -> str:
    mr = f"{record.mr_project}!{record.mr_iid} {record.mr_title}" if record.mr_project else "local range"
    skill_block = (
        f"\nRepo skill instructions loaded from {record.skill_path}:\n{record.skill_instructions[:5000]}\n"
        if record.skill_used and record.skill_instructions
        else "\nRepo skill instructions: not loaded.\n"
    )
    mcp_block = (
        f"\nProject MCP config loaded from {record.mcp_config_path}; servers: {', '.join(record.mcp_servers)}.\n"
        if record.mcp_config_path
        else "\nProject MCP config: not found.\n"
    )
    return f"""Task: {record.task}
Input: {mr}
Git range: {record.git_range}
Temporary test code allowed: {record.allow_temp_test_code}
Allowed feature environment: {ALLOWED_FEATURE_ENV_NAME}
Allowed dtools env id: {ALLOWED_FEATURE_ENV_ID}
{skill_block}{mcp_block}

Context summary:
{record.context_summary}

Required behavior:
- First call list_changed_files.
- Read relevant diffs before selecting commands.
- If package.json files are relevant, call get_package_scripts.
- When changed files include an HTML/CSS/JS UI surface, you must run an existing
  Playwright/unittest browser test before finalizing and preserve its screenshot evidence.
  Unit or API tests do not replace this browser check.
- Run only targeted safe tests through run_test_command.
- If you need to generate a Python regression test, write it exactly under `tests/`,
  for example `tests/test_agent_generated_discount_boundary.py`.
- Run generated Python tests with module syntax, for example
  `python -m unittest tests.test_agent_generated_discount_boundary -v`.
- Never write or run tests under nested `runs/` paths or absolute workspace paths.
- Do not run install, playwright install, cd, pipes, redirects, which, ls, or shell diagnostics.
- If Playwright or a browser is missing, report the missing dependency instead of trying to install it.
- Prefer package-prefix commands such as `npm --prefix <dir> test`.
- If feature environment routing is needed, use only `{ALLOWED_FEATURE_ENV_NAME}`.
- If dtools env id is needed, use only `{ALLOWED_FEATURE_ENV_ID}`.
- Never use another person's customPath, env name, or dtools envcode.
- If command output shows missing dependencies or environment blockers, read logs and explain that clearly.
- If run_test_command returns a non-zero returncode, you must immediately call
  the returned `next_required_tool`, usually `read_test_log(command_id)`, before finalizing.
- Do not mutate source branches or remote systems.
"""


def _run_missing_deterministic_commands(record: RunRecord, tools: AgentRunTools, sink: EventSink | None = None) -> None:
    planned = plan_test_commands(record.changed_files, record.workspace_repo)
    if not planned:
        return
    for command in planned:
        if _is_covered(command, [item.command for item in record.commands]):
            continue
        record.planner_trace.append(f"agent:deterministic-coverage:{command}")
        if sink is not None:
            sink.planner(f"agent:deterministic-coverage:{command}")
            cid = f"c{len(record.commands) + 1}"
            sink.command(cid, command, "start", category="deterministic-coverage")
        result = tools.run_test_command(command)
        if sink is not None:
            sink.command(
                cid,
                command,
                "ok" if result.returncode == 0 else "fail",
                category="deterministic-coverage",
                returncode=result.returncode,
                log_path=str(result.log_path.relative_to(record.run_dir)),
            )


def _is_covered(command: str, existing: list[str]) -> bool:
    if command in existing:
        return True
    package = _npm_prefix(command)
    if package is None:
        return False
    return any(_npm_prefix(item) == package for item in existing)


def _npm_prefix(command: str) -> str | None:
    parts = command.split()
    if len(parts) >= 3 and parts[0] == "npm" and parts[1] == "--prefix":
        return parts[2]
    if len(parts) >= 4 and parts[0] == "npm" and parts[1] == "test" and parts[2] == "--prefix":
        return parts[3]
    return None


def _summarize_output(output: str) -> str:
    compact = " ".join(output.split())
    if len(compact) <= 240:
        return compact
    return compact[:240] + "..."
