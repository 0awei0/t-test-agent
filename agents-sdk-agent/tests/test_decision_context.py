import json
import tempfile
import unittest
from pathlib import Path

from ai_test_officer.models import ChangedFile, CommandResult, RunRecord
from ai_test_officer.report import write_outputs


class DecisionContextTests(unittest.TestCase):
    def test_outputs_include_structured_decision_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            record = RunRecord(
                run_id="decision",
                task="验证结算折扣边界并给出发布建议",
                source_repo=Path(tmp) / "source",
                workspace_repo=run_dir / "repo",
                run_dir=run_dir,
                git_range="base..head",
                changed_files=[ChangedFile("M", "checkout.py")],
                diff_text="",
                allow_temp_test_code=False,
                commands=[
                    CommandResult(
                        "python -m unittest tests.test_checkout -v",
                        1,
                        "",
                        "AssertionError: unsafe discount accepted",
                        run_dir / "logs" / "command-01.log",
                    )
                ],
                verdict="fail",
                risk="high",
                failure_category="test-failure",
                summary="折扣边界回归测试失败。",
            )

            write_outputs(record)

            data = json.loads(record.json_path.read_text(encoding="utf-8"))
            markdown = record.report_path.read_text(encoding="utf-8")
            rendered_html = record.html_path.read_text(encoding="utf-8")

            self.assertIn("验证结算折扣边界", data["change_intent"])
            self.assertTrue(data["risk_findings"])
            self.assertTrue(data["strategy_rationale"])
            self.assertTrue(data["coverage_scope"])
            self.assertTrue(data["untested_scope"])
            self.assertIn("阻断本次发布", data["recommendations"][0])
            self.assertIn("## 决策依据", markdown)
            self.assertIn("### 未覆盖范围", markdown)
            self.assertIn("<h2>变更意图</h2>", rendered_html)
            self.assertIn("<h2>策略取舍</h2>", rendered_html)
            self.assertIn("<h2>建议动作</h2>", rendered_html)


if __name__ == "__main__":
    unittest.main()
