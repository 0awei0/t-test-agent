from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..prompts import load_prompt
from .config import configure_agents_sdk, model_provider_from_env


@dataclass(frozen=True)
class ToolSmokeResult:
    run_dir: Path
    final_output: str
    tool_calls: list[str]
    passed: bool

    @property
    def json_path(self) -> Path:
        return self.run_dir / "tool-smoke.json"


def run_tool_call_smoke(*, runs_root: Path = Path("runs"), run_id: str | None = None) -> ToolSmokeResult:
    provider = model_provider_from_env()
    if not provider.available:
        raise RuntimeError("missing model key: set ARK_API_KEY or OPENAI_API_KEY in .env")

    try:
        from agents import Agent, Runner, function_tool
    except ImportError as exc:
        raise RuntimeError("openai-agents is not installed") from exc

    if not configure_agents_sdk(provider):
        raise RuntimeError("failed to configure Agents SDK model provider")

    resolved_run_id = run_id or f"tool-smoke-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = runs_root.expanduser().resolve() / resolved_run_id
    repo_dir = run_dir / "repo"
    tests_dir = repo_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_math_smoke.py").write_text(
        """
import unittest


class MathSmokeTest(unittest.TestCase):
    def test_addition(self):
        self.assertEqual(1 + 1, 2)


if __name__ == "__main__":
    unittest.main()
""".lstrip(),
        encoding="utf-8",
    )

    tool_calls: list[str] = []

    @function_tool(strict_mode=False)
    def read_test_file() -> str:
        """Read the synthetic unittest file that should be executed."""
        tool_calls.append("read_test_file")
        return (tests_dir / "test_math_smoke.py").read_text(encoding="utf-8")

    @function_tool(strict_mode=False)
    def run_local_unittest() -> str:
        """Run the synthetic unittest suite in the local smoke workspace."""
        tool_calls.append("run_local_unittest")
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"],
            cwd=repo_dir,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        return f"exit={proc.returncode}\nstdout={proc.stdout[-4000:]}\nstderr={proc.stderr[-4000:]}"

    agent = Agent(
        name="AI Test Officer Tool Smoke",
        instructions=load_prompt("tool_smoke"),
        model=provider.model,
        tools=[read_test_file, run_local_unittest],
    )
    result = Runner.run_sync(
        agent,
        "请调用工具读取测试文件并执行本地 unittest，判断工具调用和测试执行是否正常。",
        max_turns=6,
    )
    final_output = str(getattr(result, "final_output", result))
    passed = "run_local_unittest" in tool_calls and ("exit=0" in final_output or "通过" in final_output)
    smoke = ToolSmokeResult(run_dir=run_dir, final_output=final_output, tool_calls=tool_calls, passed=passed)
    _write_result(smoke)
    return smoke


def _write_result(result: ToolSmokeResult) -> None:
    result.run_dir.mkdir(parents=True, exist_ok=True)
    result.json_path.write_text(
        json.dumps(
            {
                "run_dir": str(result.run_dir),
                "tool_calls": result.tool_calls,
                "passed": result.passed,
                "final_output": result.final_output,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
