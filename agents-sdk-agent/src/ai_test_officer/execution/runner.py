from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..agent.config import model_provider_from_env
from ..agent.planner import AgentPlannerUnavailable, run_agent_planner
from ..agent.summary import summarize_with_agents_sdk
from ..config import DEFAULT_AGENT_MAX_TURNS
from ..context import build_context_artifacts
from ..execution.failure import classify_record_failures
from ..integrations.gongfeng import (
    GongfengError,
    MrContext,
    fetch_mr_context,
    mr_git_diff,
    mr_git_range,
    resolve_local_repo_for_mr,
)
from ..mcp import read_project_mcp_config
from ..memory import build_run_memory
from ..models import RequiredToolCheck, RunRecord, SafetyCheck
from ..report import finalize_record, write_outputs
from ..skill import read_repo_skill
from ..tools import AgentRunTools, LocalTestTools
from ..tools.safety import SafetyError
from ..events import EventSink, RunPhase
from .planner import generate_temp_tests, plan_test_commands
from .workspace import create_mr_run_workspace, create_run_workspace


@dataclass(frozen=True)
class RunConfig:
    task: str
    repo: Path | None = None
    git_range: str | None = None
    runs_root: Path = Path("runs")
    allow_temp_test_code: bool = False
    run_id: str | None = None
    mr_url: str | None = None
    planner_mode: str = "auto"
    memory_mode: str = "structured"
    max_agent_turns: int = DEFAULT_AGENT_MAX_TURNS
    mr_checkout_mode: str = "auto"
    safety_probe: bool = False


def run_test_officer(config: RunConfig) -> RunRecord:
    repo, git_range, mr_context = _resolve_input(config)
    mr_diff = mr_git_diff(mr_context) if mr_context else None
    if mr_context and mr_diff:
        workspace = create_mr_run_workspace(
            source_repo=repo,
            git_range=git_range,
            runs_root=config.runs_root,
            run_id=config.run_id,
            git_diff=mr_diff,
            mr_context=mr_context,
            checkout_mode=config.mr_checkout_mode,
        )
    else:
        workspace = create_run_workspace(
            source_repo=repo,
            git_range=git_range,
            runs_root=config.runs_root,
            run_id=config.run_id,
        )
    context = build_context_artifacts(
        run_dir=workspace.run_dir,
        changed_files=workspace.git_diff.changed_files,
        diff_text=workspace.git_diff.diff_text,
        mr_context=mr_context,
    )
    skill = read_repo_skill(Path.cwd(), max_chars=6_000)
    mcp_config = read_project_mcp_config(Path.cwd())
    tools = LocalTestTools(
        repo_path=workspace.repo_dir,
        logs_dir=workspace.logs_dir,
        allow_temp_test_code=config.allow_temp_test_code,
    )
    record = RunRecord(
        run_id=workspace.run_id,
        task=config.task,
        source_repo=repo.expanduser().resolve(),
        workspace_repo=workspace.repo_dir,
        run_dir=workspace.run_dir,
        git_range=workspace.git_diff.range_spec,
        changed_files=workspace.git_diff.changed_files,
        diff_text=workspace.git_diff.diff_text,
        allow_temp_test_code=config.allow_temp_test_code,
        mr_url=mr_context.url if mr_context else None,
        mr_project=mr_context.project_path if mr_context else None,
        mr_iid=mr_context.iid if mr_context else None,
        mr_title=mr_context.title if mr_context else None,
        checkout_strategy=workspace.checkout_strategy,
        checkout_status=workspace.checkout_status,
        checkout_error=workspace.checkout_error,
        context_strategy=context.strategy,
        context_summary=context.summary,
        context_dir=context.context_dir,
        diff_index_path=context.diff_index_path,
        skill_used=skill is not None,
        skill_path=skill.path if skill else None,
        skill_instructions=skill.text if skill else "",
        mcp_config_path=mcp_config.path if mcp_config else None,
        mcp_servers=_mcp_servers(mcp_config.text) if mcp_config else [],
    )
    record.events = EventSink(record.run_dir / "events.jsonl")
    record.events.context(
        record.task,
        [
            {"status": changed.status, "path": changed.path}
            for changed in record.changed_files
        ],
    )
    record.events.phase(RunPhase.CHECKOUT, "done", detail="隔离工作区已就绪")
    record.events.isolation()
    if config.safety_probe:
        _run_safety_probe(record, tools)

    if workspace.checkout_status != "ready":
        record.planner_mode = "skipped"
        record.failure_category = "checkout-blocked"
        record.verdict = "blocked"
        record.risk = "high"
        record.blocked_reason = workspace.checkout_error
        record.summary = "MR exact-code checkout failed; tests were skipped and the report is based on diff context only."
        record.memory_summary = build_run_memory(record, mode=config.memory_mode)
        write_outputs(record)
        return record

    if config.allow_temp_test_code and config.planner_mode != "agent-strict":
        record.generated_files.extend(
            generate_temp_tests(tools=tools, changed_files=workspace.git_diff.changed_files)
        )

    agent_tools = AgentRunTools(
        local=tools,
        changed_files=workspace.git_diff.changed_files,
        context_dir=context.context_dir,
        commands=record.commands,
        generated_files=record.generated_files,
    )
    record.events.phase(RunPhase.PLANNING, "start")
    _run_planner(config, record, agent_tools)
    record.events.phase(RunPhase.PLANNING, "done")

    record.events.phase(RunPhase.EXECUTING, "start")
    record.evidence_files.extend(_collect_evidence_files(record, sink=record.events))
    record.events.phase(RunPhase.EXECUTING, "done")

    record.events.phase(RunPhase.VALIDATING, "start")
    finalize_record(record)
    classify_record_failures(record)
    _validate_agent_strict(config, record)
    _emit_agent_provenance(record)
    _emit_adaptation(record)
    record.events.phase(RunPhase.VALIDATING, "done")

    record.events.phase(RunPhase.REPORTING, "start")
    record.memory_summary = build_run_memory(record, mode=config.memory_mode)
    record.events.memory(
        record.memory_summary.mode,
        record.memory_summary.source_chars,
        record.memory_summary.summary_chars,
        record.memory_summary.compression_ratio,
        len(record.memory_summary.artifact_paths),
    )
    agent_summary = summarize_with_agents_sdk(record) if _agent_summary_enabled() else None
    write_outputs(record, agent_summary=agent_summary, finish_events=False)
    record.events.phase(RunPhase.REPORTING, "done")
    record.events.done()
    return record


def _agent_summary_enabled() -> bool:
    return os.environ.get("AI_TEST_OFFICER_ENABLE_AGENT_SUMMARY") == "1"


def _run_safety_probe(record: RunRecord, tools: LocalTestTools) -> None:
    command = "git push origin main"
    try:
        tools.run_test_command(command)
    except SafetyError as exc:
        check = SafetyCheck(
            name="synthetic_remote_write_probe",
            action="execute",
            target=command,
            status="blocked",
            blocked_by="local_safety_policy",
            reason=str(exc),
        )
        record.safety_checks.append(check)
        record.events.safety_check(
            action=check.action,
            target=check.target,
            status=check.status,
            blocked_by=check.blocked_by,
            reason=check.reason,
        )
        return
    raise RuntimeError("competition safety probe unexpectedly executed a remote mutation command")


def _emit_agent_provenance(record: RunRecord) -> None:
    record.events.provenance(
        run_id=record.run_id,
        planner_mode=record.planner_mode,
        strict_tools_passed=record.required_tool_check.passed,
        tool_calls=len(record.agent_turns),
        model_tool_calls=sum(1 for turn in record.agent_turns if turn.model_initiated),
        commands=len(record.commands),
        generated_tests=len(record.generated_files),
        evidence=len(record.evidence_files),
    )


def _emit_adaptation(record: RunRecord) -> None:
    observed = [turn.tool for turn in record.agent_turns]
    if not any(command.returncode != 0 for command in record.commands):
        return
    if "read_test_log" not in observed or not record.generated_files:
        return
    record.events.adaptation(
        kind="failure-driven-test-expansion",
        status="completed",
        detail="测试失败后读取日志，并补充隔离边界测试继续验证；失败证据保留用于发布决策。",
    )


def _run_planner(config: RunConfig, record: RunRecord, tools: AgentRunTools) -> None:
    mode = config.planner_mode
    sink = record.events
    if mode not in {"auto", "agent", "agent-strict", "deterministic"}:
        raise AgentPlannerUnavailable(f"unsupported planner mode: {mode}")
    if mode == "deterministic":
        record.planner_mode = "deterministic"
        record.planner_trace.append("deterministic:selected")
        if sink is not None:
            sink.planner("deterministic:selected")
        _run_deterministic(record, tools)
        return

    provider = model_provider_from_env()
    if mode == "auto" and not provider.available:
        record.planner_mode = "deterministic"
        record.planner_trace.append("auto:no-model; deterministic fallback")
        if sink is not None:
            sink.planner("auto:no-model; deterministic fallback")
        _run_deterministic(record, tools)
        return

    record.planner_mode = "agent-strict" if mode == "agent-strict" else "agent"
    try:
        result = run_agent_planner(
            record,
            tools,
            sink=sink,
            fallback_to_deterministic=(mode == "agent"),
            max_turns=config.max_agent_turns,
        )
        if result is not None and result.final_output:
            record.agent_final_output = result.final_output
    except AgentPlannerUnavailable:
        if mode in {"agent", "agent-strict"}:
            raise
        record.planner_mode = "deterministic"
        record.planner_trace.append("auto:agent-unavailable; deterministic fallback")
        if sink is not None:
            sink.planner("auto:agent-unavailable; deterministic fallback")
        _run_deterministic(record, tools)


def _validate_agent_strict(config: RunConfig, record: RunRecord) -> None:
    if config.planner_mode != "agent-strict":
        return
    required = ["list_changed_files", "read_file_diff", "publish_test_plan", "write_temp_test", "run_test_command"]
    if any(command.returncode != 0 for command in record.commands):
        required.append("read_test_log")
    observed = [turn.tool for turn in record.agent_turns]
    missing = [tool for tool in required if tool not in observed]
    record.required_tool_check = RequiredToolCheck(
        required=required,
        observed=observed,
        missing=missing,
        passed=not missing,
    )
    if missing:
        record.failure_category = "agent-incomplete"
        record.verdict = "needs-follow-up"
        record.risk = "high"
        record.blocked_reason = f"agent-strict missing required tools: {', '.join(missing)}"
        record.summary = "Agent strict validation did not complete the required multi-turn test loop."


def _run_deterministic(record: RunRecord, tools: AgentRunTools) -> None:
    for command in plan_test_commands(record.changed_files, record.workspace_repo):
        record.planner_trace.append(f"deterministic:run:{command}")
        if record.events is not None:
            cid = f"c{len(record.commands) + 1}"
            record.events.command(cid, command, "start", category="deterministic")
        result = tools.run_test_command(command)
        if record.events is not None:
            record.events.command(
                cid,
                command,
                "ok" if result.returncode == 0 else "fail",
                category="deterministic",
                returncode=result.returncode,
                log_path=str(result.log_path.relative_to(record.run_dir)),
            )


def _resolve_input(config: RunConfig) -> tuple[Path, str, MrContext | None]:
    if config.mr_url:
        mr_context = fetch_mr_context(config.mr_url)
        repo = resolve_local_repo_for_mr(mr_context.project_path, explicit_repo=config.repo)
        return repo, mr_git_range(mr_context), mr_context
    if config.repo is None or config.git_range is None:
        raise GongfengError("run requires either --mr-url or --repo with --git-range")
    return config.repo, config.git_range, None


def _collect_evidence_files(record: RunRecord, sink: EventSink | None = None) -> list[Path]:
    evidence_roots = [
        record.workspace_repo / "reports" / "evidence",
        record.workspace_repo / "evidence",
    ]
    files: list[Path] = []
    for root in evidence_roots:
        if not root.exists():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            files.append(path)
            if sink is not None:
                kind = "screenshot" if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"} else "log"
                sink.evidence(str(path.relative_to(record.run_dir)), kind, caption=path.name)
    return files


def _mcp_servers(text: str) -> list[str]:
    servers: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[mcp_servers.") and stripped.endswith("]"):
            servers.append(stripped.removeprefix("[mcp_servers.").removesuffix("]"))
    return servers
