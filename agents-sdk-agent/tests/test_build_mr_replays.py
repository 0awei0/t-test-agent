import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_mr_replays import _validate_reused_run


class BuildMrReplaysTests(unittest.TestCase):
    def test_accepts_reused_run_only_when_strict_contract_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            run_json = run_dir / "run.json"
            run_json.write_text(
                json.dumps(
                    {
                        "verdict": "pass",
                        "risk": "low",
                        "required_tool_check": {"passed": True},
                    }
                ),
                encoding="utf-8",
            )
            _validate_reused_run("task-43", run_dir, "pass", "low")

            run_json.write_text(
                json.dumps(
                    {
                        "verdict": "needs-follow-up",
                        "risk": "high",
                        "required_tool_check": {"passed": False},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SystemExit, "does not satisfy"):
                _validate_reused_run("task-43", run_dir, "pass", "low")


if __name__ == "__main__":
    unittest.main()
