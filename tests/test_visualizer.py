import tempfile
import unittest
from pathlib import Path

from ai_test_officer.models import TestTask
from ai_test_officer.report import write_report
from ai_test_officer.visualizer import visualize_report


class VisualizerTests(unittest.TestCase):
    def test_visualize_report_writes_html_with_core_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            evidence = repo / "reports" / "evidence"
            evidence.mkdir(parents=True)
            (evidence / "checkout-negative-total.png").write_bytes(b"fake")
            task = TestTask(
                task="场景A-fullstack",
                repo_path=repo,
                changed_files="M\tcheckout.py",
                output_path=Path("reports/fullstack-report.md"),
            )
            body = """# AI Test Officer Report

## Summary
- Verdict: fail
- Risk: high

## Changed Files / Risk Map
- checkout.py: risky discount boundary.

## Execution
- `python3 -m unittest discover -s tests -p 'test_*.py' -v`

## Findings
- Browser screenshot: reports/evidence/checkout-negative-total.png
"""
            report = write_report(task, body, dry_run=False, scenario="A-fullstack")

            html_path = visualize_report(report, report.with_suffix(".json"))
            html = html_path.read_text(encoding="utf-8")

            self.assertIn("AI Test Officer Report", html)
            self.assertIn("Scenario: A-fullstack", html)
            self.assertIn("Verdict: fail", html)
            self.assertIn("Risk: high", html)
            self.assertIn("checkout.py", html)
            self.assertIn("checkout-negative-total.png", html)


if __name__ == "__main__":
    unittest.main()
