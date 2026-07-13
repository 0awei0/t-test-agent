import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_test_officer.git_tools import collect_git_diff
from ai_test_officer.integrations.gongfeng import MrContext, MrFileChange
from ai_test_officer.models import AgentTurn, CommandResult, GeneratedFile
from ai_test_officer.runner import RunConfig, run_test_officer
from ai_test_officer.agent.planner import AgentPlannerResult, AgentPlannerUnavailable


class RunnerTests(unittest.TestCase):
    def test_collect_git_diff_reads_changed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, head = _create_buggy_repo(Path(tmp) / "repo")
            diff = collect_git_diff(repo, f"{base}..{head}")

            self.assertIn("checkout.py", diff.diff_text)
            self.assertEqual([item.path for item in diff.changed_files], ["checkout.py"])

    def test_run_creates_isolated_workspace_and_report_without_dirtying_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, base, head = _create_buggy_repo(root / "repo")
            runs_root = root / "runs"

            with _without_model_keys():
                record = run_test_officer(
                    RunConfig(
                        repo=repo,
                        git_range=f"{base}..{head}",
                        task="Analyze discount regression",
                        runs_root=runs_root,
                        allow_temp_test_code=True,
                        run_id="test-run",
                    )
                )

            self.assertEqual(record.run_dir, runs_root / "test-run")
            self.assertTrue((record.run_dir / "repo").exists())
            self.assertTrue((record.run_dir / "report.md").exists())
            self.assertTrue((record.run_dir / "run.json").exists())
            self.assertTrue((record.run_dir / "report.html").exists())
            self.assertTrue((record.run_dir / "context" / "diff-index.json").exists())
            self.assertTrue((record.workspace_repo / "tests" / "test_generated_discount_boundary.py").exists())
            self.assertEqual(record.verdict, "fail")
            self.assertEqual(record.planner_mode, "deterministic")
            self.assertEqual(_git(repo, "status", "--short"), "")
            report = record.report_path.read_text(encoding="utf-8")
            self.assertIn("Generated boundary regression test", report)
            self.assertIn("python -m unittest discover", report)
            self.assertNotIn("x" * 100, (record.run_dir / "run.json").read_text(encoding="utf-8"))

    def test_run_without_temp_test_code_does_not_write_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, base, head = _create_buggy_repo(root / "repo")

            with _without_model_keys():
                record = run_test_officer(
                    RunConfig(
                        repo=repo,
                        git_range=f"{base}..{head}",
                        task="Analyze discount regression",
                        runs_root=root / "runs",
                        allow_temp_test_code=False,
                        run_id="readonly",
                    )
                )

            self.assertFalse((record.workspace_repo / "tests" / "test_generated_discount_boundary.py").exists())
            self.assertEqual(record.verdict, "needs-follow-up")

    def test_auto_without_model_key_falls_back_to_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, base, head = _create_buggy_repo(root / "repo")

            with _without_model_keys():
                record = run_test_officer(
                    RunConfig(
                        repo=repo,
                        git_range=f"{base}..{head}",
                        task="Analyze discount regression",
                        runs_root=root / "runs",
                        run_id="auto-fallback",
                        planner_mode="auto",
                    )
                )

        self.assertEqual(record.planner_mode, "deterministic")
        self.assertIn("auto:no-model", "\n".join(record.planner_trace))

    def test_agent_mode_without_model_key_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, base, head = _create_buggy_repo(root / "repo")

            with _without_model_keys(), self.assertRaises(AgentPlannerUnavailable):
                run_test_officer(
                    RunConfig(
                        repo=repo,
                        git_range=f"{base}..{head}",
                        task="Analyze discount regression",
                        runs_root=root / "runs",
                        run_id="agent-missing-key",
                        planner_mode="agent",
                    )
                )

    def test_agent_strict_passes_when_required_tools_are_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, base, head = _create_buggy_repo(root / "repo")

            def fake_agent(record, tools, fallback_to_deterministic, max_turns, sink=None):
                self.assertFalse(fallback_to_deterministic)
                self.assertEqual(max_turns, 20)
                generated = tools.write_temp_test(
                    "tests/test_agent_generated_discount_boundary.py",
                    "import unittest\n\nclass T(unittest.TestCase):\n    def test_fail(self):\n        self.fail('agent generated failure')\n",
                    "Agent generated boundary test.",
                )
                record.agent_turns.extend(
                    [
                        AgentTurn(1, "list_changed_files", "files", "checkout.py"),
                        AgentTurn(2, "read_file_diff", "checkout.py", "removed upper bound"),
                        AgentTurn(3, "write_temp_test", "boundary test", str(generated.path)),
                    ]
                )
                result = tools.run_test_command("python -m unittest tests.test_agent_generated_discount_boundary -v")
                record.agent_turns.append(AgentTurn(4, "run_test_command", result.command, "exit 1"))
                tools.read_test_log(1)
                record.agent_turns.append(AgentTurn(5, "read_test_log", "1", "failure log"))
                return AgentPlannerResult(final_output="Agent final decision: generated test exposes regression.", used_model=True)

            with patch("ai_test_officer.execution.runner.run_agent_planner", side_effect=fake_agent):
                record = run_test_officer(
                    RunConfig(
                        repo=repo,
                        git_range=f"{base}..{head}",
                        task="Strict agent loop",
                        runs_root=root / "runs",
                        run_id="strict-pass",
                        allow_temp_test_code=True,
                        planner_mode="agent-strict",
                    )
                )

        self.assertEqual(record.planner_mode, "agent-strict")
        self.assertTrue(record.required_tool_check.passed)
        self.assertEqual(record.required_tool_check.missing, [])
        self.assertIn("generated test exposes regression", record.agent_final_output)
        self.assertEqual(record.memory_summary.status, "built")
        self.assertIsNotNone(record.memory_summary.summary_path)

    def test_agent_strict_reports_incomplete_when_required_tools_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, base, head = _create_buggy_repo(root / "repo")

            def fake_agent(record, tools, fallback_to_deterministic, max_turns, sink=None):
                record.agent_turns.append(AgentTurn(1, "list_changed_files", "files", "checkout.py"))
                log_path = record.run_dir / "logs" / "command-01.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text("failed", encoding="utf-8")
                record.commands.append(CommandResult("python -m unittest tests.test_missing -v", 1, "", "failed", log_path))
                record.generated_files.append(GeneratedFile(record.workspace_repo / "tests" / "test_missing.py", "fake"))
                return None

            with patch("ai_test_officer.execution.runner.run_agent_planner", side_effect=fake_agent):
                record = run_test_officer(
                    RunConfig(
                        repo=repo,
                        git_range=f"{base}..{head}",
                        task="Strict agent loop",
                        runs_root=root / "runs",
                        run_id="strict-missing",
                        allow_temp_test_code=True,
                        planner_mode="agent-strict",
                    )
                )

        self.assertFalse(record.required_tool_check.passed)
        self.assertEqual(record.failure_category, "agent-incomplete")
        self.assertIn("read_file_diff", record.required_tool_check.missing)
        self.assertIn("write_temp_test", record.required_tool_check.missing)
        self.assertIn("read_test_log", record.required_tool_check.missing)

    def test_mr_run_uses_rest_diff_without_local_source_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "checkout.py").write_text("VALUE = 1\n", encoding="utf-8")
            _git(repo, "init")
            _git(repo, "config", "user.email", "test@example.invalid")
            _git(repo, "config", "user.name", "Test User")
            _git(repo, "add", ".")
            _git(repo, "commit", "-m", "baseline")
            diff = """diff --git a/checkout.py b/checkout.py
index 1e6fea0..a8d40c7 100644
--- a/checkout.py
+++ b/checkout.py
@@ -1 +1 @@
-VALUE = 1
+VALUE = 2
"""
            mr = MrContext(
                url="https://git.woa.com/example/project/-/merge_requests/1",
                project_path="example/project",
                iid=1,
                id=101,
                title="change value",
                state="opened",
                source_branch="missing-source-branch",
                target_branch="master",
                source_sha=None,
                target_sha=None,
                files=[MrFileChange("M", "checkout.py", "checkout.py", diff, 1, 1)],
            )

            with (
                _without_model_keys(),
                patch("ai_test_officer.execution.runner.fetch_mr_context", return_value=mr),
                patch("ai_test_officer.execution.runner.resolve_local_repo_for_mr", return_value=repo),
            ):
                record = run_test_officer(
                    RunConfig(
                        mr_url=mr.url,
                        task="Analyze MR",
                        runs_root=root / "runs",
                        run_id="mr-rest-diff",
                        planner_mode="deterministic",
                    )
                )

            self.assertEqual((record.workspace_repo / "checkout.py").read_text(encoding="utf-8"), "VALUE = 2\n")
            self.assertEqual(record.changed_files[0].path, "checkout.py")
            self.assertEqual(record.checkout_strategy, "target-apply-diff")
            self.assertEqual(record.checkout_status, "ready")

    def test_mr_run_prefers_source_ref_inside_isolated_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "checkout.py").write_text("VALUE = 1\n", encoding="utf-8")
            _git(repo, "init")
            _git(repo, "config", "user.email", "test@example.invalid")
            _git(repo, "config", "user.name", "Test User")
            _git(repo, "add", ".")
            _git(repo, "commit", "-m", "baseline")
            _git(repo, "checkout", "-b", "feature")
            (repo / "checkout.py").write_text("VALUE = 2\n", encoding="utf-8")
            _git(repo, "add", ".")
            _git(repo, "commit", "-m", "change value")
            feature_sha = _git(repo, "rev-parse", "HEAD")
            diff = _git(repo, "diff", "master", "feature")
            _git(repo, "checkout", "master")
            mr = MrContext(
                url="https://git.woa.com/example/project/-/merge_requests/2",
                project_path="example/project",
                iid=2,
                id=102,
                title="source branch checkout",
                state="opened",
                source_branch="feature",
                target_branch="master",
                source_sha=feature_sha,
                target_sha=None,
                files=[MrFileChange("M", "checkout.py", "checkout.py", diff, 1, 1)],
            )

            with (
                _without_model_keys(),
                patch("ai_test_officer.execution.runner.fetch_mr_context", return_value=mr),
                patch("ai_test_officer.execution.runner.resolve_local_repo_for_mr", return_value=repo),
            ):
                record = run_test_officer(
                    RunConfig(
                        mr_url=mr.url,
                        task="Analyze MR",
                        runs_root=root / "runs",
                        run_id="mr-source-ref",
                        planner_mode="deterministic",
                    )
                )

            self.assertEqual((record.workspace_repo / "checkout.py").read_text(encoding="utf-8"), "VALUE = 2\n")
            self.assertEqual(record.checkout_strategy, "source-ref")
            self.assertEqual(record.checkout_status, "ready")
            self.assertEqual(_git(repo, "branch", "--show-current"), "master")

    def test_mr_diff_only_generates_blocked_report_without_running_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "checkout.py").write_text("VALUE = 1\n", encoding="utf-8")
            _git(repo, "init")
            _git(repo, "config", "user.email", "test@example.invalid")
            _git(repo, "config", "user.name", "Test User")
            _git(repo, "add", ".")
            _git(repo, "commit", "-m", "baseline")
            diff = """diff --git a/checkout.py b/checkout.py
index 1e6fea0..a8d40c7 100644
--- a/checkout.py
+++ b/checkout.py
@@ -1 +1 @@
-VALUE = 1
+VALUE = 2
"""
            mr = MrContext(
                url="https://git.woa.com/example/project/-/merge_requests/3",
                project_path="example/project",
                iid=3,
                id=103,
                title="diff only",
                state="opened",
                source_branch="missing",
                target_branch="master",
                source_sha=None,
                target_sha=None,
                files=[MrFileChange("M", "checkout.py", "checkout.py", diff, 1, 1)],
            )

            with (
                _without_model_keys(),
                patch("ai_test_officer.execution.runner.fetch_mr_context", return_value=mr),
                patch("ai_test_officer.execution.runner.resolve_local_repo_for_mr", return_value=repo),
            ):
                record = run_test_officer(
                    RunConfig(
                        mr_url=mr.url,
                        task="Analyze MR",
                        runs_root=root / "runs",
                        run_id="mr-diff-only",
                        planner_mode="deterministic",
                        mr_checkout_mode="diff-only",
                    )
                )

            self.assertEqual(record.checkout_strategy, "diff-only")
            self.assertEqual(record.checkout_status, "blocked")
            self.assertEqual(record.failure_category, "checkout-blocked")
            self.assertEqual(record.commands, [])
            self.assertTrue(record.report_path.exists())


def _create_buggy_repo(repo: Path) -> tuple[Path, str, str]:
    repo.mkdir(parents=True)
    (repo / "checkout.py").write_text(
        """
def discounted_total(total_cents, discount_percent):
    if discount_percent < 0 or discount_percent > 100:
        raise ValueError("discount must be 0-100")
    return int(total_cents * (100 - discount_percent) / 100)
""".lstrip(),
        encoding="utf-8",
    )
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "checkout.py").write_text(
        """
def discounted_total(total_cents, discount_percent):
    if discount_percent < 0:
        raise ValueError("discount must be non-negative")
    return int(total_cents * (100 - discount_percent) / 100)
""".lstrip(),
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "allow boosted discounts")
    head = _git(repo, "rev-parse", "HEAD")
    return repo, base, head


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return proc.stdout.strip()


def _without_model_keys():
    return patch.dict(
        os.environ,
        {
            "AI_TEST_OFFICER_API_KEY": "",
            "OPENAI_API_KEY": "",
            "ARK_API_KEY": "",
        },
        clear=False,
    )


if __name__ == "__main__":
    unittest.main()
