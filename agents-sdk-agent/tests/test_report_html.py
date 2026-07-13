import tempfile
import unittest
from pathlib import Path

from ai_test_officer.models import AgentTurn, ChangedFile, CommandResult, GeneratedFile, RequiredToolCheck, RunRecord
from ai_test_officer.report import render_html, render_markdown


class ReportHtmlTests(unittest.TestCase):
    def test_structured_html_hides_agent_timeline_and_sanitizes_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "runs" / "demo"
            repo = run_dir / "repo"
            record = RunRecord(
                run_id="demo",
                task="showcase",
                source_repo=root / "business-source",
                workspace_repo=repo,
                run_dir=run_dir,
                git_range="HEAD~1..HEAD",
                changed_files=[ChangedFile("M", "checkout.py")],
                diff_text="",
                allow_temp_test_code=True,
                planner_mode="agent-strict",
                agent_turns=[
                    AgentTurn(1, "list_changed_files", "changed file list", "checkout.py"),
                    AgentTurn(2, "read_file_diff", "checkout.py", "discount guard removed"),
                    AgentTurn(3, "write_temp_test", "tests/test_generated.py", "written"),
                    AgentTurn(4, "run_test_command", "python -m unittest tests.test_generated -v", "failed"),
                    AgentTurn(5, "read_test_log", "1", "AssertionError"),
                ],
                required_tool_check=RequiredToolCheck(
                    required=[
                        "list_changed_files",
                        "read_file_diff",
                        "write_temp_test",
                        "run_test_command",
                        "read_test_log",
                    ],
                    observed=[
                        "list_changed_files",
                        "read_file_diff",
                        "write_temp_test",
                        "run_test_command",
                        "read_test_log",
                    ],
                    passed=True,
                ),
                generated_files=[
                    GeneratedFile(repo / "tests" / "test_generated.py", "Agent generated regression test.")
                ],
                evidence_files=[repo / "reports" / "evidence" / "checkout.png"],
                commands=[
                    CommandResult(
                        "python -m unittest tests.test_generated -v",
                        1,
                        "",
                        "AssertionError: ValueError not raised",
                        run_dir / "logs" / "command-01.log",
                    )
                ],
                verdict="fail",
                risk="high",
                summary="Generated regression test failed.",
                failure_category="test-failure",
                agent_final_output=(
                    "### 发布判断\n\n"
                    "- **阻断合并**：折扣边界被移除。\n"
                    "- 复现命令：`python -m unittest tests.test_generated_retry -v`\n\n"
                    "```text\nAssertionError: ValueError not raised\n```\n"
                    "\n| 风险 | 建议 |\n| --- | --- |\n| 高 | 修复后再发布 |\n"
                    "<script>alert('unsafe')</script>"
                ),
            )

            html = render_html(render_markdown(record), record=record)

            self.assertIn("决策摘要", html)
            self.assertIn('href="dashboard/?mode=static"', html)
            self.assertIn("观看 Agent 动态执行复盘", html)
            self.assertIn("体验合成 TAPD / 工蜂任务", html)
            self.assertIn("变更意图", html)
            self.assertIn("主要风险", html)
            self.assertIn("策略取舍", html)
            self.assertIn("已覆盖范围", html)
            self.assertIn("未覆盖范围", html)
            self.assertIn("建议动作", html)
            self.assertNotIn("Agent 多轮过程", html)
            self.assertNotIn("<h2>规划轨迹</h2>", html)
            self.assertNotIn("为什么这不是纯 workflow", html)
            self.assertIn("Agent 判断", html)
            self.assertIn("<h3>发布判断</h3>", html)
            self.assertIn("<strong>阻断合并</strong>", html)
            self.assertIn("<code>python -m unittest tests.test_generated_retry -v</code>", html)
            self.assertNotIn("test&lt;em&gt;generated&lt;/em&gt;", html)
            self.assertIn("<pre><code>AssertionError: ValueError not raised</code></pre>", html)
            self.assertIn('<div class="markdown-table"><table>', html)
            self.assertIn("<th>风险</th>", html)
            self.assertIn('<td data-label="建议">修复后再发布</td>', html)
            self.assertIn("&lt;script&gt;alert(&#x27;unsafe&#x27;)&lt;/script&gt;", html)
            self.assertNotIn("<script>alert('unsafe')</script>", html)
            self.assertIn("Agent 生成的临时测试", html)
            self.assertIn("关键工具", html)
            self.assertIn("原始仓库", html)
            self.assertIn("危险操作", html)
            self.assertIn('class="evidence-trigger"', html)
            self.assertIn('id="evidence-modal"', html)
            self.assertNotIn('checkout.png" target="_blank"', html)
            self.assertIn("tests/test_generated.py", html)
            self.assertIn("&lt;source-repo&gt;", html)
            self.assertIn("&lt;isolated-workspace&gt;", html)
            self.assertNotIn(str(record.source_repo), html)
            self.assertNotIn(str(record.workspace_repo), html)


if __name__ == "__main__":
    unittest.main()
