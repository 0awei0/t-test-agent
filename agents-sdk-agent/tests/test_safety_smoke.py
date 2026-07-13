import json
import tempfile
import unittest
from pathlib import Path

from ai_test_officer.safety_smoke import run_safety_smoke


class SafetySmokeTests(unittest.TestCase):
    def test_safety_smoke_blocks_unsafe_actions_and_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_safety_smoke(runs_root=root / "runs", run_id="safety-run")

            self.assertTrue(result.passed)
            self.assertGreaterEqual(result.blocked, 9)
            self.assertGreaterEqual(result.allowed, 2)
            self.assertTrue((root / "runs" / "safety-run" / "report.md").exists())
            self.assertTrue((root / "runs" / "safety-run" / "report.html").exists())

            data = json.loads((root / "runs" / "safety-run" / "run.json").read_text(encoding="utf-8"))
            statuses = {item["status"] for item in data["safety_checks"]}
            targets = {item["target"] for item in data["safety_checks"]}
            self.assertIn("blocked", statuses)
            self.assertIn("allowed", statuses)
            self.assertIn("git push", targets)
            self.assertIn("../evil.py", targets)
            self.assertNotIn("unexpected-allowed", statuses)

            report = (root / "runs" / "safety-run" / "report.md").read_text(encoding="utf-8")
            self.assertIn("安全边界", report)
            self.assertIn("Safety smoke passed", report)


if __name__ == "__main__":
    unittest.main()
