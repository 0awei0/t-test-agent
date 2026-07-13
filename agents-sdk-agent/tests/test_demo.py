import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_test_officer.demo import (
    DemoRunConfig,
    create_agent_loop_demo,
    create_fullstack_demo,
    create_investigation_demo,
    create_release_guard_demo,
    run_investigation_demo,
    run_agent_loop_demo,
    run_fullstack_demo,
    run_release_guard_demo,
)


class FullstackDemoTests(unittest.TestCase):
    def test_create_fullstack_demo_has_buggy_last_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_fullstack_demo(Path(tmp))

            diff = _git(repo, "diff", "HEAD~1", "HEAD")
            changed = _git(repo, "diff", "--name-only", "HEAD~1", "HEAD")

            self.assertIn("discount_percent > 100", diff)
            self.assertEqual(changed.strip(), "checkout.py")
            self.assertTrue((repo / "tests" / "test_api_checkout.py").exists())
            self.assertTrue((repo / "tests" / "test_browser_checkout.py").exists())

    def test_create_agent_loop_demo_requires_agent_generated_boundary_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_agent_loop_demo(Path(tmp))

            diff = _git(repo, "diff", "HEAD~1", "HEAD")
            changed = _git(repo, "diff", "--name-only", "HEAD~1", "HEAD")

            self.assertIn("discount_percent > 100", diff)
            self.assertEqual(changed.strip(), "checkout.py")
            self.assertTrue((repo / "tests" / "test_checkout.py").exists())
            self.assertFalse((repo / "tests" / "test_agent_generated_discount_boundary.py").exists())

    def test_agent_loop_demo_records_a_real_safety_policy_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with _without_model_keys():
                record = run_agent_loop_demo(
                    DemoRunConfig(
                        demo_root=root / "demos",
                        planner_mode="deterministic",
                        allow_temp_test_code=True,
                        runs_root=root / "runs",
                        run_id="safety-agent-loop",
                    )
                )

            blocked = [item for item in record.safety_checks if item.status == "blocked"]
            self.assertEqual(len(blocked), 1)
            self.assertEqual(blocked[0].target, "git push origin main")
            event_types = [json.loads(line)["type"] for line in record.events.path.read_text().splitlines()]
            self.assertIn("safety_check", event_types)

    def test_run_fullstack_demo_generates_report_and_records_skill_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_fullstack_demo(root / "demos")
            with _without_model_keys():
                record = run_fullstack_demo(
                    DemoRunConfig(
                        demo_root=root / "demos",
                        planner_mode="deterministic",
                        allow_temp_test_code=True,
                        runs_root=root / "runs",
                        run_id="demo-run",
                    )
                )

            self.assertEqual(record.verdict, "fail")
            self.assertTrue(record.skill_used)
            self.assertIn("playwright", record.mcp_servers)
            self.assertTrue(record.html_path.exists())
            report = record.report_path.read_text(encoding="utf-8")
            self.assertIn("Skill 已加载: `True`", report)
            self.assertIn("MCP 服务:", report)
            self.assertIn("python -m unittest discover", report)

    def test_release_guard_demo_has_three_changed_business_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_release_guard_demo(Path(tmp))

            changed = _git(repo, "diff", "--name-only", "HEAD~1", "HEAD").splitlines()
            self.assertEqual(changed, ["orders.py", "server.py", "static/index.html"])
            self.assertIn("coupon_percent > 60", _git(repo, "diff", "HEAD~1", "HEAD"))
            self.assertTrue((repo / "tests" / "test_orders.py").exists())
            self.assertTrue((repo / "tests" / "test_api.py").exists())
            self.assertTrue((repo / "tests" / "test_browser.py").exists())
            subprocess.run([sys.executable, "-m", "py_compile", "orders.py", "server.py"], cwd=repo, check=True)

    def test_release_guard_demo_blocks_release_with_deterministic_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_release_guard_demo(root / "demos")
            with _without_model_keys():
                record = run_release_guard_demo(
                    DemoRunConfig(
                        demo_root=root / "demos",
                        planner_mode="deterministic",
                        allow_temp_test_code=True,
                        runs_root=root / "runs",
                        run_id="release-guard",
                    )
                )

            self.assertEqual(record.verdict, "fail")
            self.assertEqual(record.risk, "high")
            self.assertEqual([item.path for item in record.changed_files], ["orders.py", "server.py", "static/index.html"])
            self.assertTrue(record.events.path.exists())
            self.assertNotIn("IndentationError", record.commands[0].stderr)

    def test_investigation_cases_expose_contract_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for scenario, marker in (("promotion-chain", "coupon_percent > 60"), ("refund-guard", '"customer"')):
                repo = create_investigation_demo(root / "demos", scenario)
                self.assertIn(marker, _git(repo, "diff", "HEAD~1", "HEAD"))
                with _without_model_keys():
                    record = run_investigation_demo(
                        DemoRunConfig(
                            demo_root=root / "demos",
                            planner_mode="deterministic",
                            allow_temp_test_code=True,
                            runs_root=root / "runs",
                            run_id=f"{scenario}-run",
                        ),
                        scenario,
                    )
                self.assertEqual(record.verdict, "fail")
                self.assertEqual(record.risk, "high")
                self.assertIn("contract", record.commands[0].stderr.lower())

    def test_repaired_investigation_cases_pass_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for scenario, marker in (("promotion-chain-pass", "coupon_percent > 30"), ("refund-guard-pass", 'actor_role != "support"')):
                repo = create_investigation_demo(root / "demos", scenario)
                self.assertIn(marker, _git(repo, "diff", "HEAD~1", "HEAD"))
                with _without_model_keys():
                    record = run_investigation_demo(
                        DemoRunConfig(
                            demo_root=root / "demos",
                            planner_mode="deterministic",
                            allow_temp_test_code=True,
                            runs_root=root / "runs",
                            run_id=f"{scenario}-run",
                        ),
                        scenario,
                    )
                self.assertEqual(record.verdict, "pass")
                self.assertEqual(record.risk, "low")

    def test_repaired_release_guard_passes_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = create_release_guard_demo(root / "demos", repaired=True)
            self.assertIn("coupon_percent > 30", _git(repo, "diff", "HEAD~1", "HEAD"))
            with _without_model_keys():
                record = run_release_guard_demo(
                    DemoRunConfig(
                        demo_root=root / "demos",
                        planner_mode="deterministic",
                        allow_temp_test_code=True,
                        runs_root=root / "runs",
                        run_id="release-guard-pass",
                    ),
                    repaired=True,
                )
            self.assertEqual(record.verdict, "pass")
            self.assertEqual(record.risk, "low")


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], check=True, text=True, capture_output=True)
    return proc.stdout


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
