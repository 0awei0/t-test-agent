import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_test_officer.wecom_bot import (
    build_notification_content,
    build_wecom_payload,
    redacted_webhook_target,
    render_dry_run,
    resolve_wecom_webhook,
    send_wecom_payload,
)


class WeComBotTests(unittest.TestCase):
    def test_build_markdown_payload(self) -> None:
        payload = build_wecom_payload("hello", msgtype="markdown")

        self.assertEqual(payload["msgtype"], "markdown")
        self.assertEqual(payload["markdown"]["content"], "hello")

    def test_build_notification_content_includes_report_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.md"
            report_path.write_text(
                "<!-- generated-by: ai_test_officer -->\n\n## Summary\n- Verdict: fail\n",
                encoding="utf-8",
            )

            content = build_notification_content(
                message="场景A报告",
                report_path=report_path,
            )

            self.assertIn("场景A报告", content)
            self.assertIn("Report:", content)
            self.assertIn("## Summary", content)
            self.assertNotIn("generated-by", content)

    def test_build_notification_content_omits_prompt_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.md"
            report_path.write_text(
                "\n".join(
                    [
                        "# AI Test Officer Report",
                        "",
                        "## Summary",
                        "- Verdict: needs-follow-up",
                        "",
                        "## Recommended Next Steps",
                        "- Run without --dry-run.",
                        "",
                        "## Prompt Preview",
                        "You are AI Test Officer, a full-chain testing agent.",
                        "Repository: /tmp/demo",
                    ]
                ),
                encoding="utf-8",
            )

            content = build_notification_content(
                message="场景A报告",
                report_path=report_path,
            )

            self.assertIn("## Summary", content)
            self.assertIn("## Recommended Next Steps", content)
            self.assertNotIn("## Prompt Preview", content)
            self.assertNotIn("You are AI Test Officer", content)
            self.assertNotIn("Repository: /tmp/demo", content)

    def test_build_notification_content_summarizes_dry_run_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.md"
            report_path.write_text(
                "\n".join(
                    [
                        "<!-- generated-by: ai_test_officer -->",
                        "<!-- mode: dry-run -->",
                        "",
                        "# AI Test Officer Report",
                        "## Scope",
                        "- Generated the prompt that would be sent to Codex.",
                        "## Prompt Preview",
                        "You are AI Test Officer, a full-chain testing agent.",
                    ]
                ),
                encoding="utf-8",
            )

            content = build_notification_content(
                message="场景A报告",
                report_path=report_path,
            )

            self.assertIn("Dry-run report was generated locally.", content)
            self.assertNotIn("Generated the prompt", content)
            self.assertNotIn("Prompt Preview", content)
            self.assertNotIn("You are AI Test Officer", content)

    def test_build_notification_content_uses_section_summary_without_truncated_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.md"
            report_path.write_text(
                "\n".join(
                    [
                        "# AI Test Officer Report",
                        "",
                        "## Summary",
                        "- Verdict: fail",
                        "- Risk: high",
                        "- " + "blocking regression " * 80,
                        "",
                        "## Changed Files / Risk Map",
                        "- checkout.py: " + "risk " * 120,
                        "",
                        "## Execution",
                        "- python -m unittest discover failed.",
                        "",
                        "## Findings",
                        "- discount_percent > 100 no longer raises.",
                        "",
                        "## Recommended Next Steps",
                        "- Restore the upper-bound validation.",
                    ]
                ),
                encoding="utf-8",
            )

            content = build_notification_content(
                message="场景A报告",
                report_path=report_path,
            )

            self.assertIn("## Summary", content)
            self.assertIn("## Findings", content)
            self.assertIn("更多内容见完整报告", content)
            self.assertNotIn("<truncated>", content)

    def test_render_dry_run_redacts_key(self) -> None:
        payload = build_wecom_payload("secret-free")
        webhook = resolve_wecom_webhook("https://example.test/send?key=real-key", "")

        rendered = render_dry_run(payload, webhook)

        self.assertIn("key=<redacted>", rendered)
        self.assertNotIn("real-key", rendered)
        self.assertIn("secret-free", rendered)

    def test_redacted_target_handles_missing_key(self) -> None:
        self.assertIn("key=<not-set>", redacted_webhook_target(None))

    def test_resolve_wecom_webhook_prefers_full_url(self) -> None:
        webhook = resolve_wecom_webhook(
            "https://example.test/cgi-bin/webhook/send?key=abc&debug=1",
            "fallback",
        )

        self.assertIsNotNone(webhook)
        assert webhook is not None
        self.assertEqual(webhook.base_url, "https://example.test/cgi-bin/webhook/send")
        self.assertEqual(webhook.key, "abc")
        self.assertEqual(webhook.redacted_target, "https://example.test/cgi-bin/webhook/send?key=<redacted>")

    def test_send_wecom_payload_posts_json(self) -> None:
        class FakeResponse:
            status = 200

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"errcode": 0, "errmsg": "ok"}).encode()

        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            result = send_wecom_payload(
                "abc 123",
                build_wecom_payload("hello"),
                base_url="https://example.test/send",
            )

        self.assertTrue(result.ok)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.test/send?key=abc%20123")
        self.assertEqual(request.get_method(), "POST")


if __name__ == "__main__":
    unittest.main()
