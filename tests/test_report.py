import tempfile
import unittest
from pathlib import Path

from ai_test_officer.models import TestTask
from ai_test_officer.report import dry_run_report, write_report


class ReportTests(unittest.TestCase):
    def test_write_report_creates_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            task = TestTask(
                task="dry run",
                repo_path=repo,
                output_path=Path("reports/test-report.md"),
            )

            path = write_report(task, dry_run_report("hello"), dry_run=True)

            self.assertTrue(path.exists())
            self.assertIn("dry-run", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

