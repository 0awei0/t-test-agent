import os
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from typing import get_origin
from unittest.mock import patch

from ai_test_officer.agent.planner import _LiveRunHooks, _planner_timeout, run_agent_planner
from ai_test_officer.models import ChangedFile, CommandResult, RunRecord
from ai_test_officer.tools import AgentRunTools, LocalTestTools


class AgentPlannerTests(unittest.TestCase):
    def test_planner_timeout_is_safe_in_background_thread(self) -> None:
        errors: list[Exception] = []

        def run() -> None:
            try:
                with _planner_timeout(1):
                    pass
            except Exception as exc:  # pragma: no cover - assertion captures regressions
                errors.append(exc)

        thread = threading.Thread(target=run)
        thread.start()
        thread.join()
        self.assertEqual(errors, [])

    def test_live_hooks_use_agents_sdk_base_type(self) -> None:
        from agents import RunHooks

        self.assertIsInstance(_LiveRunHooks(None), get_origin(RunHooks) or RunHooks)

    def test_agent_planner_records_tool_calls_and_runs_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            tests = repo / "tests"
            context = root / "context"
            logs = root / "logs"
            tests.mkdir(parents=True)
            context.mkdir()
            logs.mkdir()
            (tests / "test_ok.py").write_text(
                "import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            (context / "diff-index.json").write_text(
                '[{"path":"tests/test_ok.py","artifact":"diffs/test_ok.py.diff"}]',
                encoding="utf-8",
            )
            (context / "diffs").mkdir()
            (context / "diffs" / "test_ok.py.diff").write_text("+test\n", encoding="utf-8")
            record = RunRecord(
                run_id="agent",
                task="Analyze",
                source_repo=repo,
                workspace_repo=repo,
                run_dir=root,
                git_range="base..head",
                changed_files=[ChangedFile("M", "tests/test_ok.py")],
                diff_text="",
                allow_temp_test_code=False,
                context_dir=context,
                context_summary="summary",
            )
            tools = AgentRunTools(
                LocalTestTools(repo, logs, allow_temp_test_code=False),
                record.changed_files,
                context,
                record.commands,
                record.generated_files,
            )
            tools.local.run_test_command = lambda command: CommandResult(  # type: ignore[method-assign]
                command,
                0,
                "ok",
                "",
                logs / "command-01.log",
            )

            with _fake_agents_modules(), patch.dict(
                os.environ,
                {"ARK_API_KEY": "ark", "AI_TEST_OFFICER_MODEL": "doubao-test"},
                clear=True,
            ):
                result = run_agent_planner(record, tools, fallback_to_deterministic=False, max_turns=21)

        self.assertTrue(result.used_model)
        self.assertIn("list_changed_files", record.tools_used)
        self.assertIn(
            "run_test_command:uv run python -m unittest discover -s tests -p test_*.py -v",
            record.tools_used,
        )
        self.assertEqual(record.commands[0].returncode, 0)

    def test_failed_log_must_be_read_before_another_test_command(self) -> None:
        observed: dict[str, str] = {}

        def exercise_tools(agent, prompt, max_turns=12, hooks=None, **kwargs):
            first = agent.tools[5]("python -m unittest tests.test_one -v")
            observed["blocked"] = agent.tools[5]("python -m unittest tests.test_two -v")
            agent.tools[6](1)
            observed["after_read"] = agent.tools[5]("python -m unittest tests.test_two -v")
            return types.SimpleNamespace(final_output=first)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            context = root / "context"
            logs = root / "logs"
            repo.mkdir()
            context.mkdir()
            logs.mkdir()
            (context / "diff-index.json").write_text("[]", encoding="utf-8")
            record = RunRecord(
                run_id="agent-failure-log",
                task="Analyze",
                source_repo=repo,
                workspace_repo=repo,
                run_dir=root,
                git_range="base..head",
                changed_files=[],
                diff_text="",
                allow_temp_test_code=False,
                context_dir=context,
            )
            tools = AgentRunTools(
                LocalTestTools(repo, logs, allow_temp_test_code=False),
                [],
                context,
                record.commands,
                record.generated_files,
            )

            def fail(command: str) -> CommandResult:
                log_path = logs / f"command-{len(record.commands) + 1:02d}.log"
                log_path.write_text("failure details", encoding="utf-8")
                return CommandResult(command, 1, "", "failure", log_path)

            tools.local.run_test_command = fail  # type: ignore[method-assign]
            with _fake_agents_modules(exercise_tools), patch.dict(
                os.environ,
                {"ARK_API_KEY": "ark", "AI_TEST_OFFICER_MODEL": "doubao-test"},
                clear=True,
            ):
                run_agent_planner(record, tools, fallback_to_deterministic=False, max_turns=21)

        self.assertIn("read_test_log(1)", observed["blocked"])
        self.assertNotIn("previous failed command log", observed["after_read"])
        self.assertEqual(len(record.commands), 2)


def _fake_agents_modules(run_sync_override=None):
    class FakeAgent:
        def __init__(self, *, name, instructions, model, tools):
            self.name = name
            self.instructions = instructions
            self.model = model
            self.tools = tools

    class FakeRunner:
        @staticmethod
        def run_sync(agent, prompt, max_turns=12, hooks=None, **kwargs):
            if run_sync_override is not None:
                return run_sync_override(agent, prompt, max_turns=max_turns, hooks=hooks, **kwargs)
            assert max_turns == 21
            agent.tools[0]()
            agent.tools[1]("tests/test_ok.py")
            agent.tools[5]("uv run python -m unittest discover -s tests -p test_*.py -v")
            return types.SimpleNamespace(final_output="planned")

    def function_tool(strict_mode=False):
        def decorator(func):
            return func

        return decorator

    class FakeAsyncOpenAI:
        def __init__(self, *, base_url, api_key):
            self.base_url = base_url
            self.api_key = api_key

    fake_agents = types.SimpleNamespace(
        Agent=FakeAgent,
        Runner=FakeRunner,
        function_tool=function_tool,
        set_default_openai_api=lambda api: None,
        set_default_openai_client=lambda client, use_for_tracing=True: None,
        set_default_openai_key=lambda key, use_for_tracing=True: None,
        set_tracing_disabled=lambda disabled: None,
    )
    fake_openai = types.SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI)
    return patch.dict(sys.modules, {"agents": fake_agents, "openai": fake_openai})


if __name__ == "__main__":
    unittest.main()
