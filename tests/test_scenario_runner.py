import subprocess
import tempfile
import unittest
from pathlib import Path

from ai_test_officer.scenario_runner import (
    ScenarioRunConfig,
    create_scenario_demos,
    run_scenario,
    task_for_demo,
)


class ScenarioRunnerTests(unittest.TestCase):
    def test_create_all_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            demos = create_scenario_demos(Path(tmp), "all")

            self.assertEqual(set(demos), {"A", "A-fullstack", "B", "C"})
            self.assertTrue((demos["A"].repo_path / "checkout.py").exists())
            self.assertTrue((demos["A-fullstack"].repo_path / "server.py").exists())
            self.assertTrue((demos["A-fullstack"].repo_path / "static" / "index.html").exists())
            self.assertTrue(
                (demos["A-fullstack"].repo_path / "tests" / "test_browser_checkout.py").exists()
            )
            self.assertTrue((demos["B"].repo_path / "prd.md").exists())
            self.assertTrue((demos["C"].repo_path / "patrol.md").exists())

    def test_scenario_a_task_contains_last_commit_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            demo = create_scenario_demos(Path(tmp), "A")["A"]
            task = task_for_demo(demo)

            self.assertEqual(task.diff_label, "HEAD~1..HEAD")
            self.assertIn("M\tcheckout.py", task.changed_files or "")
            self.assertIn("-    if discount_percent < 0 or discount_percent > 100", task.diff_text or "")

    def test_scenario_a_fullstack_task_contains_last_commit_diff_and_guide(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            demo = create_scenario_demos(Path(tmp), "A-fullstack")["A-fullstack"]
            task = task_for_demo(demo)

            self.assertEqual(task.diff_label, "HEAD~1..HEAD")
            self.assertIn("M\tcheckout.py", task.changed_files or "")
            self.assertIn("fullstack-testing.md", str(task.requirement_path))
            self.assertTrue((demo.repo_path / "tests" / "test_api.py").exists())

    def test_run_scenarios_dry_run_creates_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            report_a = run_scenario("A", ScenarioRunConfig(root, dry_run=True)).report_path
            report_fullstack = run_scenario(
                "A-fullstack", ScenarioRunConfig(root, dry_run=True)
            ).report_path
            report_b = run_scenario("B", ScenarioRunConfig(root, dry_run=True)).report_path
            report_c = run_scenario("C", ScenarioRunConfig(root, dry_run=True)).report_path

            text_a = report_a.read_text(encoding="utf-8")
            text_fullstack = report_fullstack.read_text(encoding="utf-8")
            text_b = report_b.read_text(encoding="utf-8")
            text_c = report_c.read_text(encoding="utf-8")
            self.assertIn("Scenario A mode", text_a)
            self.assertIn("## Changed Files Input", text_a)
            self.assertIn("M\tcheckout.py", text_a)
            self.assertIn("Playwright MCP", text_fullstack)
            self.assertIn("tests/test_browser_checkout.py", text_fullstack)
            self.assertIn("## Requirement Input", text_b)
            self.assertIn("discount_percent` 必须在 0 到 100 之间", text_b)
            self.assertIn("## Requirement Input", text_c)
            self.assertIn("核心链路巡检说明", text_c)
            self.assertTrue(report_fullstack.with_suffix(".json").exists())

    def test_synthetic_scenario_tests_fail_on_seeded_bugs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            demos = create_scenario_demos(Path(tmp), "all")

            result_a = _run_unittest(demos["A"].repo_path)
            result_fullstack = _run_unittest(demos["A-fullstack"].repo_path)
            result_b = _run_unittest(demos["B"].repo_path)
            result_c = _run_unittest(demos["C"].repo_path)

            self.assertNotEqual(result_a.returncode, 0)
            self.assertNotEqual(result_fullstack.returncode, 0)
            self.assertNotEqual(result_b.returncode, 0)
            self.assertNotEqual(result_c.returncode, 0)
            self.assertIn("ValueError not raised", result_a.stdout + result_a.stderr)
            self.assertIn("ValueError not raised", result_fullstack.stdout + result_fullstack.stderr)
            self.assertIn("ValueError not raised", result_b.stdout + result_b.stderr)
            self.assertIn("inventory_sync", result_c.stdout + result_c.stderr)


def _run_unittest(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


if __name__ == "__main__":
    unittest.main()
