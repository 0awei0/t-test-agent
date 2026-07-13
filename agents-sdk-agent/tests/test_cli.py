import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ai_test_officer.cli import _hold_dashboard, main
from ai_test_officer.models import RequiredToolCheck
from test_runner import _create_buggy_repo


class CliTests(unittest.TestCase):
    def test_run_command_writes_expected_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, base, head = _create_buggy_repo(root / "repo")
            with (
                patch.dict(
                    os.environ,
                    {
                        "AI_TEST_OFFICER_API_KEY": "",
                        "OPENAI_API_KEY": "",
                        "ARK_API_KEY": "",
                    },
                    clear=False,
                ),
                contextlib.redirect_stdout(io.StringIO()) as stdout,
            ):
                main(
                    [
                        "run",
                        "--repo",
                        str(repo),
                        "--git-range",
                        f"{base}..{head}",
                        "--task",
                        "Analyze discount regression",
                        "--runs-root",
                        str(root / "runs"),
                        "--env",
                        str(root / "missing.env"),
                        "--run-id",
                        "cli-run",
                        "--allow-temp-test-code",
                        "--notify-dry-run",
                    ]
                )

            rendered = stdout.getvalue()
            self.assertIn("Run:", rendered)
            self.assertIn("Verdict: fail", rendered)
            self.assertIn("WeCom dry-run payload:", rendered)
            self.assertTrue((root / "runs" / "cli-run" / "report.md").exists())

    def test_smoke_tools_command_prints_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_result = Mock(
                run_dir=root / "runs" / "tool-smoke",
                json_path=root / "runs" / "tool-smoke" / "tool-smoke.json",
                tool_calls=["read_test_file", "run_local_unittest"],
                passed=True,
                final_output="工具调用和 unittest 均通过",
            )

            with (
                patch("ai_test_officer.cli.run_tool_call_smoke", return_value=fake_result),
                contextlib.redirect_stdout(io.StringIO()) as stdout,
            ):
                main(
                    [
                        "smoke",
                        "tools",
                        "--runs-root",
                        str(root / "runs"),
                        "--env",
                        str(root / "missing.env"),
                    ]
                )

            rendered = stdout.getvalue()
            self.assertIn("Tool calls: read_test_file, run_local_unittest", rendered)
            self.assertIn("Passed: True", rendered)

    def test_smoke_mcp_command_prints_config_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".codex").mkdir()
            (root / ".codex" / "config.toml").write_text(
                "\n".join(
                    [
                        "[mcp_servers.tapd_mcp_http]",
                        "[mcp_servers.iWiki]",
                        "[mcp_servers.gongfeng]",
                        "[mcp_servers.playwright]",
                    ]
                ),
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                main(["smoke", "mcp", "--repo-root", str(root)])

            rendered = stdout.getvalue()
            self.assertIn('"passed": true', rendered)
            self.assertIn("playwright", rendered)

    def test_smoke_safety_command_prints_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                main(
                    [
                        "smoke",
                        "safety",
                        "--runs-root",
                        str(root / "runs"),
                        "--run-id",
                        "cli-safety",
                    ]
                )

            rendered = stdout.getvalue()
            self.assertIn("Passed: True", rendered)
            self.assertIn("Blocked:", rendered)
            self.assertTrue((root / "runs" / "cli-safety" / "report.html").exists())

    def test_demo_create_and_run_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                main(
                    [
                        "demo",
                        "create",
                        "--scenario",
                        "fullstack",
                        "--demo-root",
                        str(root / "demos"),
                    ]
                )

            self.assertIn("Demo:", stdout.getvalue())
            self.assertTrue((root / "demos" / "fullstack" / ".git").exists())

            with (
                patch.dict(
                    os.environ,
                    {
                        "AI_TEST_OFFICER_API_KEY": "",
                        "OPENAI_API_KEY": "",
                        "ARK_API_KEY": "",
                    },
                    clear=False,
                ),
                contextlib.redirect_stdout(io.StringIO()) as run_stdout,
            ):
                main(
                    [
                        "demo",
                        "run",
                        "--scenario",
                        "fullstack",
                        "--demo-root",
                        str(root / "demos"),
                        "--runs-root",
                        str(root / "runs"),
                        "--run-id",
                        "cli-demo",
                        "--planner-mode",
                        "deterministic",
                        "--allow-temp-test-code",
                        "--env",
                        str(root / "missing.env"),
                    ]
                )

            rendered = run_stdout.getvalue()
            self.assertIn("Verdict: fail", rendered)
            self.assertTrue((root / "runs" / "cli-demo" / "report.html").exists())

    def test_demo_showcase_exports_fue_and_can_render_wecom_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_record = Mock(
                run_dir=root / "runs" / "showcase",
                report_path=root / "runs" / "showcase" / "report.md",
                json_path=root / "runs" / "showcase" / "run.json",
                html_path=root / "runs" / "showcase" / "report.html",
                verdict="fail",
                risk="high",
                summary="Generated test exposed the checkout regression.",
                planner_mode="agent-strict",
                changed_files=[],
                generated_files=[],
                detail_url=None,
                required_tool_check=RequiredToolCheck(
                    required=["list_changed_files"],
                    observed=["list_changed_files"],
                    passed=True,
                ),
            )
            fake_export = Mock(
                project_root=root / "fue",
                public_dir=root / "fue" / "public",
                deploy_doc_path=root / "fue" / "FUE_DEPLOY.md",
            )

            with (
                patch("ai_test_officer.cli.run_agent_loop_demo", return_value=fake_record),
                patch("ai_test_officer.cli.export_fue_static_project", return_value=fake_export) as export,
                contextlib.redirect_stdout(io.StringIO()) as stdout,
            ):
                main(
                    [
                        "demo",
                        "showcase",
                        "--scenario",
                        "agent-loop",
                        "--runs-root",
                        str(root / "runs"),
                        "--export-fue",
                        str(root / "fue"),
                        "--detail-url",
                        "https://ai-test-officer.fue.woa.com/index.html",
                        "--notify-dry-run",
                        "--env",
                        str(root / "missing.env"),
                    ]
                )

            rendered = stdout.getvalue()
            export.assert_called_once()
            self.assertIn("FUE project:", rendered)
            self.assertIn("WeCom dry-run payload:", rendered)
            self.assertIn("Required tool check: True", rendered)
            self.assertEqual(fake_record.detail_url, "https://ai-test-officer.fue.woa.com/index.html")

    def test_demo_showcase_publish_sets_detail_link_before_notify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_record = Mock(
                run_dir=root / "runs" / "showcase",
                report_path=root / "runs" / "showcase" / "report.md",
                json_path=root / "runs" / "showcase" / "run.json",
                html_path=root / "runs" / "showcase" / "report.html",
                verdict="fail",
                risk="high",
                summary="Generated test exposed the checkout regression.",
                planner_mode="agent-strict",
                changed_files=[],
                generated_files=[],
                detail_url=None,
                required_tool_check=RequiredToolCheck(passed=True),
            )

            def fake_publish(record, args):
                record.detail_url = "http://report.example/showcase/index.html"

            with (
                patch("ai_test_officer.cli.run_agent_loop_demo", return_value=fake_record),
                patch("ai_test_officer.cli._publish_from_args", side_effect=fake_publish),
                contextlib.redirect_stdout(io.StringIO()) as stdout,
            ):
                main(
                    [
                        "demo",
                        "showcase",
                        "--scenario",
                        "agent-loop",
                        "--runs-root",
                        str(root / "runs"),
                        "--publish",
                        "--report-base-url",
                        "http://report.example",
                        "--notify-dry-run",
                        "--env",
                        str(root / "missing.env"),
                    ]
                )

            rendered = stdout.getvalue()
            self.assertIn("[查看完整测试报告](http://report.example/showcase/index.html)", rendered)

    def test_demo_showcase_send_requires_clickable_detail_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_record = Mock(
                run_dir=root / "runs" / "showcase",
                report_path=root / "runs" / "showcase" / "report.md",
                json_path=root / "runs" / "showcase" / "run.json",
                html_path=root / "runs" / "showcase" / "report.html",
                verdict="fail",
                risk="high",
                summary="Generated test exposed the checkout regression.",
                planner_mode="agent-strict",
                changed_files=[],
                generated_files=[],
                detail_url=None,
                required_tool_check=RequiredToolCheck(passed=True),
            )

            with (
                patch("ai_test_officer.cli.run_agent_loop_demo", return_value=fake_record),
                patch("ai_test_officer.cli.send_wecom_markdown") as send,
                self.assertRaises(SystemExit) as raised,
            ):
                main(
                    [
                        "demo",
                        "showcase",
                        "--scenario",
                        "agent-loop",
                        "--runs-root",
                        str(root / "runs"),
                        "--send",
                        "--env",
                        str(root / "missing.env"),
                    ]
                )

            self.assertIn("requires a clickable report URL", str(raised.exception))
            send.assert_not_called()

    def test_demo_doctor_command_fails_on_bad_fue_public(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            public = root / "public"
            public.mkdir()
            (public / "index.html").write_text("/data/workspace/t-test-agent", encoding="utf-8")
            (public / "report.md").write_text("# Report\n", encoding="utf-8")
            (public / "public-run.json").write_text('{"commands":[{"stderr":"full"}]}', encoding="utf-8")
            (public / "run.json").write_text("{}", encoding="utf-8")

            with (
                contextlib.redirect_stdout(io.StringIO()) as stdout,
                self.assertRaises(SystemExit) as raised,
            ):
                main(
                    [
                        "demo",
                        "doctor",
                        "--fue-public",
                        str(public),
                        "--require-detail-url",
                        "--env",
                        str(root / "missing.env"),
                    ]
                )

            self.assertEqual(raised.exception.code, 1)
            rendered = stdout.getvalue()
            self.assertIn("FAIL: detail_url", rendered)
            self.assertIn("FAIL: fue_full_run_json", rendered)

    def test_mr_url_command_passes_mr_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_record = Mock(
                run_dir=root / "runs" / "mr-run",
                report_path=root / "runs" / "mr-run" / "report.md",
                json_path=root / "runs" / "mr-run" / "run.json",
                html_path=root / "runs" / "mr-run" / "report.html",
                verdict="needs-follow-up",
            )
            captured = []

            def fake_run(config):
                captured.append(config)
                return fake_record

            with (
                patch("ai_test_officer.cli.run_test_officer", side_effect=fake_run),
                contextlib.redirect_stdout(io.StringIO()) as stdout,
            ):
                main(
                    [
                        "run",
                        "--mr-url",
                        "https://git.woa.com/example/project/-/merge_requests/10",
                        "--task",
                        "Analyze MR",
                        "--planner-mode",
                        "agent",
                        "--runs-root",
                        str(root / "runs"),
                        "--env",
                        str(root / "missing.env"),
                        "--allow-temp-test-code",
                        "--mr-checkout-mode",
                        "source-ref",
                    ]
                )

            self.assertEqual(captured[0].mr_url, "https://git.woa.com/example/project/-/merge_requests/10")
            self.assertEqual(captured[0].max_agent_turns, 20)
            self.assertIsNone(captured[0].git_range)
            self.assertEqual(captured[0].planner_mode, "agent")
            self.assertEqual(captured[0].mr_checkout_mode, "source-ref")
            self.assertIn("Verdict: needs-follow-up", stdout.getvalue())

    def test_batch_mr_command_passes_batch_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_file = root / "candidates.md"
            candidate_file.write_text("https://git.woa.com/example/project/-/merge_requests/10", encoding="utf-8")
            fake_summary = Mock(
                results=[Mock(status="ok")],
                runs_root=root / "runs",
                markdown_path=root / "runs" / "batch-summary.md",
                json_path=root / "runs" / "batch-summary.json",
            )
            captured = []

            def fake_batch(config):
                captured.append(config)
                return fake_summary

            with (
                patch("ai_test_officer.cli.run_mr_batch", side_effect=fake_batch),
                contextlib.redirect_stdout(io.StringIO()) as stdout,
            ):
                main(
                    [
                        "batch",
                        "mr",
                        "--candidate-file",
                        str(candidate_file),
                        "--runs-root",
                        str(root / "runs"),
                        "--planner-mode",
                        "agent",
                        "--allow-temp-test-code",
                        "--max-agent-turns",
                        "24",
                        "--limit",
                        "1",
                        "--mr-checkout-mode",
                        "target-apply-diff",
                        "--env",
                        str(root / "missing.env"),
                    ]
                )

            self.assertEqual(captured[0].candidate_file, candidate_file)
            self.assertEqual(captured[0].max_agent_turns, 24)
            self.assertEqual(captured[0].limit, 1)
            self.assertEqual(captured[0].mr_checkout_mode, "target-apply-diff")
            self.assertIn("Total: 1 OK: 1 Error: 0", stdout.getvalue())

    def test_hold_dashboard_ignores_interrupt_during_shutdown(self) -> None:
        server = Mock()
        server.shutdown_evt.is_set.return_value = True
        server.shutdown.side_effect = KeyboardInterrupt

        _hold_dashboard(server)

        server.shutdown_evt.set.assert_called_once()
        server.shutdown.assert_called_once()


if __name__ == "__main__":
    unittest.main()
