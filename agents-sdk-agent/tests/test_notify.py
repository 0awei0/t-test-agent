import json
import unittest
from pathlib import Path

from ai_test_officer.models import ChangedFile, RunRecord
from ai_test_officer.notify import build_wecom_markdown, send_wecom_markdown


class NotifyTests(unittest.TestCase):
    def test_wecom_dry_run_does_not_require_webhook_and_redacts_secret_names(self) -> None:
        result = send_wecom_markdown("ARK_API_KEY=secret-value\nhello", dry_run=True)

        self.assertFalse(result.delivered)
        self.assertTrue(result.dry_run)
        payload = json.loads(result.body)
        self.assertEqual(payload["msgtype"], "markdown")
        self.assertIn("ARK_API_KEY=<redacted>", payload["markdown"]["content"])
        self.assertNotIn("secret-value", result.body)

    def test_build_wecom_markdown_is_compact(self) -> None:
        record = RunRecord(
            run_id="notify-run",
            task="Analyze change",
            source_repo=Path("/source"),
            workspace_repo=Path("/workspace"),
            run_dir=Path("runs/notify-run"),
            git_range="base..head",
            changed_files=[ChangedFile("M", "checkout.py")],
            diff_text="",
            allow_temp_test_code=True,
            verdict="fail",
            risk="high",
            summary="1 test command failed.",
        )

        markdown = build_wecom_markdown(record)

        self.assertIn("AI 测试官", markdown)
        self.assertIn("场景:", markdown)
        self.assertIn("checkout.py", markdown)
        self.assertIn("runs/notify-run/report.md", markdown)
        self.assertNotIn("/source", markdown)
        self.assertNotIn("/workspace", markdown)

    def test_build_wecom_markdown_prefers_detail_url(self) -> None:
        record = RunRecord(
            run_id="notify-run",
            task="Analyze change",
            source_repo=Path("/source"),
            workspace_repo=Path("/workspace"),
            run_dir=Path("runs/notify-run"),
            git_range="base..head",
            changed_files=[ChangedFile("M", "checkout.py")],
            diff_text="",
            allow_temp_test_code=True,
            verdict="fail",
            risk="high",
            summary="1 test command failed.",
            detail_url="https://internal.example/reports/notify-run/index.html",
        )

        markdown = build_wecom_markdown(record)

        self.assertIn("[查看完整测试报告](https://internal.example/reports/notify-run/index.html)", markdown)
        self.assertIn("场景:", markdown)
        self.assertNotIn("runs/notify-run/report.md", markdown)
        self.assertNotIn("/source", markdown)
        self.assertNotIn("prompt", markdown.lower())
        self.assertNotIn("diff", markdown.lower())


if __name__ == "__main__":
    unittest.main()
