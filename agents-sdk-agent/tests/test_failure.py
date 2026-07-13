import unittest
from pathlib import Path

from ai_test_officer.execution.failure import classify_command_failure, classify_record_failures
from ai_test_officer.models import CommandResult, RunRecord


class FailureClassificationTests(unittest.TestCase):
    def test_detects_dependency_missing_from_jest(self) -> None:
        category, reason = classify_command_failure(
            CommandResult("npm test", 127, "", "sh: line 1: jest: command not found", Path("log"))
        )

        self.assertEqual(category, "dependency-missing")
        self.assertIn("jest", reason)

    def test_detects_dependency_missing_from_node_module(self) -> None:
        category, reason = classify_command_failure(
            CommandResult("npm test", 1, "", "Error: Cannot find module '@playwright/test'", Path("log"))
        )

        self.assertEqual(category, "dependency-missing")
        self.assertIn("@playwright/test", reason)

    def test_detects_dependency_missing_from_missing_npm_script(self) -> None:
        category, reason = classify_command_failure(
            CommandResult("npm run test:e2e", 1, "", "npm ERR! Missing script: \"test:e2e\"", Path("log"))
        )

        self.assertEqual(category, "dependency-missing")
        self.assertIn("Missing script", reason)

    def test_detects_environment_missing_from_timeout(self) -> None:
        category, reason = classify_command_failure(
            CommandResult("go test ./service", 124, "", "command timed out after 120s\n(timeout)", Path("log"))
        )

        self.assertEqual(category, "environment-missing")
        self.assertIn("timed out", reason)

    def test_dependency_missing_marks_record_blocked(self) -> None:
        record = RunRecord(
            run_id="failure",
            task="Analyze",
            source_repo=Path("/source"),
            workspace_repo=Path("/workspace"),
            run_dir=Path("/runs/failure"),
            git_range="base..head",
            changed_files=[],
            diff_text="",
            allow_temp_test_code=False,
            commands=[
                CommandResult("npm test", 127, "", "sh: line 1: jest: command not found", Path("log"))
            ],
            verdict="fail",
            risk="high",
        )

        classify_record_failures(record)

        self.assertEqual(record.verdict, "blocked")
        self.assertEqual(record.failure_category, "dependency-missing")
        self.assertIn("does not prove", record.summary)


if __name__ == "__main__":
    unittest.main()
