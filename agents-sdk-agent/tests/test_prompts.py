import unittest

from ai_test_officer.prompts import PromptLoadError, load_prompt


class PromptTests(unittest.TestCase):
    def test_loads_packaged_prompt(self) -> None:
        self.assertIn("AI Test Officer", load_prompt("test_officer"))

    def test_reporter_prompt_defaults_to_chinese(self) -> None:
        prompt = load_prompt("reporter")

        self.assertIn("报告正文默认使用中文", prompt)
        self.assertIn("文件名、命令、枚举值", prompt)
        self.assertIn("先给结论", prompt)

    def test_missing_prompt_has_clear_error(self) -> None:
        with self.assertRaises(PromptLoadError):
            load_prompt("missing")


if __name__ == "__main__":
    unittest.main()
