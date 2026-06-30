import json
import tempfile
import unittest
from pathlib import Path

from ai_test_officer.models import TestTask
from ai_test_officer.report import dry_run_report, run_json_path_for, write_report


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
            self.assertTrue(run_json_path_for(path).exists())

    def test_write_report_creates_safe_run_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            task = TestTask(
                task="scenario",
                repo_path=repo,
                changed_files="M\tcheckout.py",
                output_path=Path("reports/test-report.md"),
            )
            body = """# AI Test Officer Report

## Summary
- Verdict: fail
- Risk: high

## Changed Files / Risk Map
- checkout.py: discount boundary risk.

## Execution
- `python3 -m unittest discover -s tests -p 'test_*.py' -v`

## Findings
- Screenshot: reports/evidence/checkout-negative-total.png
"""

            path = write_report(task, body, dry_run=False, scenario="A-fullstack")
            data = json.loads(run_json_path_for(path).read_text(encoding="utf-8"))

            self.assertEqual(data["scenario"], "A-fullstack")
            self.assertEqual(data["verdict"], "fail")
            self.assertEqual(data["risk"], "high")
            self.assertEqual(data["changed_files"], ["M\tcheckout.py"])
            self.assertIn("checkout-negative-total.png", data["artifacts"][0]["path"])
            self.assertNotIn("Prompt Preview", data["sections"])


if __name__ == "__main__":
    unittest.main()
