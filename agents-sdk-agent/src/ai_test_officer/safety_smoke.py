from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import ChangedFile, RunRecord, SafetyCheck
from .report import finalize_record, write_outputs
from .tools.local import LocalTestTools
from .tools.safety import SafetyError


@dataclass(frozen=True)
class SafetySmokeResult:
    record: RunRecord
    blocked: int
    allowed: int
    passed: bool


def run_safety_smoke(*, runs_root: Path = Path("runs"), run_id: str | None = None) -> SafetySmokeResult:
    resolved_run_id = run_id or f"safety-smoke-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = runs_root.expanduser().resolve() / resolved_run_id
    source_repo = run_dir / "source"
    workspace_repo = run_dir / "repo"
    logs_dir = run_dir / "logs"
    for path in (source_repo, workspace_repo, logs_dir):
        path.mkdir(parents=True, exist_ok=True)
    _write_demo_repo(source_repo)
    if workspace_repo.exists():
        shutil.rmtree(workspace_repo)
    shutil.copytree(source_repo, workspace_repo)

    record = RunRecord(
        run_id=resolved_run_id,
        task="Safety guardrails smoke: prove the agent can only test in an isolated workspace.",
        source_repo=source_repo,
        workspace_repo=workspace_repo,
        run_dir=run_dir,
        git_range="safety-smoke",
        changed_files=[ChangedFile("M", "checkout.py")],
        diff_text="Safety smoke uses a synthetic checkout module; no raw business diff is stored.",
        allow_temp_test_code=True,
        planner_mode="safety-smoke",
        failure_category="passed",
        context_strategy="synthetic-safety-smoke",
        context_summary=(
            "Synthetic workspace used to validate command and write guardrails. "
            "The source directory is copied before execution and never mutated."
        ),
    )
    tools = LocalTestTools(workspace_repo, logs_dir, allow_temp_test_code=True)
    disabled_write_tools = LocalTestTools(workspace_repo, logs_dir, allow_temp_test_code=False)

    _record_allowed_write(record, tools, "tests/test_generated_safety.py")
    _record_allowed_command(record, tools, "python -m unittest tests.test_checkout -v")

    for command in _dangerous_commands():
        _record_blocked_command(record, tools, command)

    for path, tool in [
        ("checkout.py", tools),
        ("../evil.py", tools),
        ("tests/test_disabled.py", disabled_write_tools),
    ]:
        _record_blocked_write(record, tool, path)

    _record_source_readonly(record, source_repo)
    finalize_record(record)
    record.verdict = "pass" if _all_expected_blocks_observed(record) else "fail"
    record.risk = "low" if record.verdict == "pass" else "high"
    record.summary = _summary(record)
    write_outputs(record)
    blocked = sum(1 for item in record.safety_checks if item.status == "blocked")
    allowed = sum(1 for item in record.safety_checks if item.status == "allowed")
    return SafetySmokeResult(record=record, blocked=blocked, allowed=allowed, passed=record.verdict == "pass")


def _write_demo_repo(repo: Path) -> None:
    (repo / "tests").mkdir(parents=True, exist_ok=True)
    (repo / "checkout.py").write_text(
        "\n".join(
            [
                "def discounted_total(total_cents, discount_percent):",
                "    if discount_percent < 0 or discount_percent > 100:",
                "        raise ValueError('discount must be between 0 and 100')",
                "    return int(total_cents * (100 - discount_percent) / 100)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "tests" / "test_checkout.py").write_text(
        "\n".join(
            [
                "import unittest",
                "from checkout import discounted_total",
                "",
                "",
                "class CheckoutTests(unittest.TestCase):",
                "    def test_discounted_total(self):",
                "        self.assertEqual(discounted_total(10000, 25), 7500)",
                "",
                "",
                "if __name__ == '__main__':",
                "    unittest.main()",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _dangerous_commands() -> list[str]:
    return [
        "git push",
        "git checkout main",
        "git reset --hard",
        "rm -rf .",
        "curl http://example.invalid",
        "deployment-cli publish --env production",
    ]


def _record_allowed_write(record: RunRecord, tools: LocalTestTools, path: str) -> None:
    generated = tools.write_temp_file(
        path,
        "def test_generated_safety_placeholder():\n    assert True\n",
        "Safety smoke allowed temporary test write.",
    )
    record.generated_files.append(generated)
    record.safety_checks.append(
        SafetyCheck(
            name="write_temp_test_allowed",
            action="write",
            target=path,
            status="allowed",
            blocked_by="none",
            reason="temporary test path is inside the isolated workspace allowlist",
        )
    )


def _record_allowed_command(record: RunRecord, tools: LocalTestTools, command: str) -> None:
    result = tools.run_test_command(command)
    record.commands.append(result)
    record.safety_checks.append(
        SafetyCheck(
            name="run_test_command_allowed",
            action="execute",
            target=command,
            status="allowed",
            blocked_by="none",
            reason=f"test whitelist accepted command; exit={result.returncode}",
        )
    )


def _record_blocked_command(record: RunRecord, tools: LocalTestTools, command: str) -> None:
    try:
        tools.run_test_command(command)
    except SafetyError as exc:
        record.safety_checks.append(
            SafetyCheck(
                name="run_test_command_blocked",
                action="execute",
                target=command,
                status="blocked",
                blocked_by="local_safety_policy",
                reason=str(exc),
            )
        )
        return
    record.safety_checks.append(
        SafetyCheck(
            name="run_test_command_blocked",
            action="execute",
            target=command,
            status="unexpected-allowed",
            blocked_by="none",
            reason="dangerous command unexpectedly executed",
        )
    )


def _record_blocked_write(record: RunRecord, tools: LocalTestTools, path: str) -> None:
    try:
        tools.write_temp_file(path, "# should not be written\n", "Safety smoke blocked write.")
    except SafetyError as exc:
        record.safety_checks.append(
            SafetyCheck(
                name="write_temp_test_blocked",
                action="write",
                target=path,
                status="blocked",
                blocked_by="local_safety_policy",
                reason=str(exc),
            )
        )
        return
    record.safety_checks.append(
        SafetyCheck(
            name="write_temp_test_blocked",
            action="write",
            target=path,
            status="unexpected-allowed",
            blocked_by="none",
            reason="unsafe write unexpectedly succeeded",
        )
    )


def _record_source_readonly(record: RunRecord, source_repo: Path) -> None:
    mutated = (source_repo / "tests" / "test_generated_safety.py").exists() or (source_repo / "evil.py").exists()
    record.safety_checks.append(
        SafetyCheck(
            name="source_repo_readonly",
            action="inspect",
            target=str(source_repo),
            status="blocked" if mutated else "allowed",
            blocked_by="isolated_workspace",
            reason="source repo was not mutated" if not mutated else "source repo was unexpectedly mutated",
        )
    )


def _all_expected_blocks_observed(record: RunRecord) -> bool:
    blocked = [item for item in record.safety_checks if item.status == "blocked"]
    unexpected = [item for item in record.safety_checks if item.status == "unexpected-allowed"]
    return len(blocked) >= len(_dangerous_commands()) + 3 and not unexpected


def _summary(record: RunRecord) -> str:
    blocked = sum(1 for item in record.safety_checks if item.status == "blocked")
    allowed = sum(1 for item in record.safety_checks if item.status == "allowed")
    unexpected = sum(1 for item in record.safety_checks if item.status == "unexpected-allowed")
    if unexpected:
        return f"Safety smoke failed: {unexpected} unsafe action(s) unexpectedly passed."
    return f"Safety smoke passed: {blocked} unsafe action(s) blocked and {allowed} safe action(s) allowed."
