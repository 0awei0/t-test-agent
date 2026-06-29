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


if __name__ == "__main__":
    unittest.main()

