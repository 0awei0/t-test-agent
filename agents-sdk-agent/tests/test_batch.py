import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ai_test_officer.batch import BatchMrConfig, parse_mr_urls_from_markdown, run_mr_batch


class BatchTests(unittest.TestCase):
    def test_parse_mr_urls_deduplicates_preserving_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidates.md"
            path.write_text(
                "\n".join(
                    [
                        "| [change](https://git.woa.com/example/project/-/merge_requests/10) |",
                        "detail https://git.woa.com/example/project/-/merge_requests/10",
                        "next https://git.woa.com/example/project/-/merge_requests/11",
                    ]
                ),
                encoding="utf-8",
            )

            urls = parse_mr_urls_from_markdown(path)

        self.assertEqual(
            urls,
            [
                "https://git.woa.com/example/project/-/merge_requests/10",
                "https://git.woa.com/example/project/-/merge_requests/11",
            ],
        )

    def test_batch_continues_after_one_mr_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_file = root / "candidates.md"
            candidate_file.write_text(
                "\n".join(
                    [
                        "https://git.woa.com/example/project/-/merge_requests/10",
                        "https://git.woa.com/example/project/-/merge_requests/11",
                    ]
                ),
                encoding="utf-8",
            )
            fake_record = Mock(
                report_path=root / "runs" / "project-10" / "report.md",
                json_path=root / "runs" / "project-10" / "run.json",
                html_path=root / "runs" / "project-10" / "report.html",
                verdict="blocked",
                risk="high",
                failure_category="dependency-missing",
                blocked_reason="jest: command not found",
                commands=[],
                checkout_strategy="source-ref",
                checkout_status="ready",
                checkout_error="",
            )

            def fake_run(config):
                if config.mr_url.endswith("/11"):
                    raise RuntimeError("no permission")
                return fake_record

            with patch("ai_test_officer.batch.run_test_officer", side_effect=fake_run):
                summary = run_mr_batch(
                    BatchMrConfig(
                        candidate_file=candidate_file,
                        runs_root=root / "runs",
                        task="test",
                        planner_mode="agent",
                        allow_temp_test_code=True,
                    )
                )

            self.assertEqual([item.status for item in summary.results], ["ok", "error"])
            self.assertEqual(summary.results[0].checkout_strategy, "source-ref")
            self.assertEqual(summary.results[0].demo_fit, "low")
            self.assertTrue(summary.markdown_path.exists())
            self.assertTrue(summary.json_path.exists())
            markdown = summary.markdown_path.read_text(encoding="utf-8")
            self.assertIn("Demo Fit", markdown)
            data = summary.json_path.read_text(encoding="utf-8")
            self.assertIn("demo_fit", data)


if __name__ == "__main__":
    unittest.main()
