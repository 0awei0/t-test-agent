import unittest
from pathlib import Path

from ai_test_officer.models import TestTask
from ai_test_officer.prompts import build_test_officer_prompt


class PromptTests(unittest.TestCase):
    def test_prompt_includes_safety_and_report_shape(self) -> None:
        task = TestTask(task="Check the checkout flow", repo_path=Path("."))

        prompt = build_test_officer_prompt(task)

        self.assertIn("AI Test Officer", prompt)
        self.assertIn("Do not edit source files", prompt)
        self.assertIn("Final response format", prompt)
        self.assertIn("## Test Strategy", prompt)
        self.assertIn("Use $ai-test-officer when available.", prompt)
        self.assertIn("Playwright MCP", prompt)
        self.assertIn("uv run --with playwright", prompt)
        self.assertIn("reports/evidence/", prompt)

    def test_prompt_includes_scenario_a_context_for_git_diff(self) -> None:
        task = TestTask(
            task="Analyze the last commit",
            repo_path=Path("."),
            diff_text="diff --git a/checkout.py b/checkout.py\n+buggy change",
            diff_label="HEAD~1..HEAD",
            changed_files="M\tcheckout.py",
        )

        prompt = build_test_officer_prompt(task)

        self.assertIn("Scenario A mode", prompt)
        self.assertIn("## Changed Files / Risk Map", prompt)
        self.assertIn("## Changed Files Input", prompt)
        self.assertIn("M\tcheckout.py", prompt)
        self.assertIn("## Git diff Input", prompt)
        self.assertIn("+buggy change", prompt)


if __name__ == "__main__":
    unittest.main()
