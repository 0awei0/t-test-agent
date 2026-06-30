import argparse
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_test_officer.cli import _add_common_args, main
from ai_test_officer.demo_scenarios import ScenarioDemo
from ai_test_officer.scenario_runner import ScenarioRunResult


class CliTests(unittest.TestCase):
    def test_diff_inputs_are_mutually_exclusive(self) -> None:
        parser = argparse.ArgumentParser()
        _add_common_args(parser)

        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(
                    [
                        "--task",
                        "scenario A",
                        "--repo",
                        str(Path(".")),
                        "--diff",
                        "diff.txt",
                        "--last-commit",
                    ]
                )

    def test_notify_dry_run_prints_payload_without_key(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            main(
                [
                    "notify",
                    "--env",
                    "/tmp/ai-test-officer-missing-env",
                    "--message",
                    "hello",
                    "--dry-run",
                ]
            )

        rendered = stdout.getvalue()
        self.assertIn("Mode: dry-run", rendered)
        self.assertIn("key=<not-set>", rendered)
        self.assertIn('"msgtype": "markdown"', rendered)

    def test_notify_requires_key_when_sending(self) -> None:
        with self.assertRaisesRegex(SystemExit, "WECOM_WEBHOOK_URL or WECOM_WEBHOOK_KEY is not set"):
            main(
                [
                    "notify",
                    "--env",
                    "/tmp/ai-test-officer-missing-env",
                    "--message",
                    "hello",
                ]
            )

    def test_scenario_create_all_prints_demo_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                main(["scenario", "create", "--scenario", "all", "--demo-root", tmp])

            rendered = stdout.getvalue()
            self.assertIn("Scenario A:", rendered)
            self.assertIn("Scenario A-fullstack:", rendered)
            self.assertIn("Scenario B:", rendered)
            self.assertIn("Scenario C:", rendered)

    def test_scenario_run_dry_run_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                main(["scenario", "run", "--scenario", "A", "--demo-root", tmp, "--dry-run"])

            rendered = stdout.getvalue()
            self.assertIn("Scenario A completed (dry-run).", rendered)
            self.assertIn("scenario-a-report.md", rendered)

    def test_scenario_run_visualize_writes_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                main(
                    [
                        "scenario",
                        "run",
                        "--scenario",
                        "A-fullstack",
                        "--demo-root",
                        tmp,
                        "--dry-run",
                        "--visualize",
                    ]
                )

            rendered = stdout.getvalue()
            self.assertIn("Scenario A-fullstack completed (dry-run).", rendered)
            self.assertIn("Wrote HTML report:", rendered)
            html_path = (
                Path(tmp)
                / "scenario-a-fullstack"
                / "reports"
                / "scenario-a-fullstack-report.html"
            )
            self.assertTrue(html_path.exists())

    def test_visualize_command_uses_sidecar_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "repo" / "reports" / "report.md"
            report_path.parent.mkdir(parents=True)
            report_path.write_text("# AI Test Officer Report\n", encoding="utf-8")
            report_path.with_suffix(".json").write_text(
                '{"schema_version":1,"scenario":"A","verdict":"pass","risk":"low","timeline":[]}',
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                main(["visualize", "--report", str(report_path)])

            self.assertIn("Wrote HTML report:", stdout.getvalue())
            self.assertTrue(report_path.with_suffix(".html").exists())

    def test_scenario_send_requires_webhook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.md"
            report_path.write_text("# AI Test Officer Report\n", encoding="utf-8")

            fake_result = ScenarioRunResult(
                scenario="A",
                demo=ScenarioDemo("A", Path(tmp), "task"),
                report_path=report_path,
                mode="codex-sdk",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                with mock.patch("ai_test_officer.cli.run_scenario", return_value=fake_result):
                    with self.assertRaisesRegex(SystemExit, "omit --send or configure .env"):
                        main(
                            [
                                "scenario",
                                "run",
                                "--scenario",
                                "A",
                                "--demo-root",
                                tmp,
                                "--env",
                                "/tmp/ai-test-officer-missing-env",
                                "--send",
                            ]
                        )

    def test_scenario_send_rejects_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(SystemExit, "run without --dry-run to send a test report"):
                main(
                    [
                        "scenario",
                        "run",
                        "--scenario",
                        "A",
                        "--demo-root",
                        tmp,
                        "--dry-run",
                        "--send",
                    ]
                )


if __name__ == "__main__":
    unittest.main()
