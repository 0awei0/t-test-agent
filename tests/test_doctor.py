import tempfile
import unittest
from pathlib import Path

from ai_test_officer.doctor import CheckResult, exit_code, load_env, render_summary


class DoctorTests(unittest.TestCase):
    def test_load_env_reads_dotenv_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "# comment",
                        "TAPD_ACCESS_TOKEN=abc123",
                        "QUOTED='value with spaces'",
                        "EMPTY=",
                    ]
                ),
                encoding="utf-8",
            )

            env = load_env(env_path, base={})

            self.assertEqual(env["TAPD_ACCESS_TOKEN"], "abc123")
            self.assertEqual(env["QUOTED"], "value with spaces")
            self.assertEqual(env["EMPTY"], "")

    def test_render_summary_and_exit_code(self) -> None:
        results = [
            CheckResult("TAPD MCP", True, "initialize returned serverInfo"),
            CheckResult("Gongfeng REST", False, "GONGFENG_ACCESS_TOKEN is not set"),
        ]

        summary = render_summary(results)

        self.assertIn("[PASS] TAPD MCP", summary)
        self.assertIn("[FAIL] Gongfeng REST", summary)
        self.assertEqual(exit_code(results), 1)

    def test_exit_code_success(self) -> None:
        self.assertEqual(exit_code([CheckResult("Playwright MCP", True, "ok")]), 0)


if __name__ == "__main__":
    unittest.main()
