import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_test_officer.showcase_doctor import run_demo_doctor


class ShowcaseDoctorTests(unittest.TestCase):
    def test_clean_fue_public_passes_with_warnings_for_optional_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            public = Path(tmp) / "public"
            public.mkdir()
            (public / "index.html").write_text("<html>ok</html>", encoding="utf-8")
            (public / "report.md").write_text("# Report\n", encoding="utf-8")
            (public / "public-run.json").write_text(
                json.dumps(
                    {
                        "run_id": "showcase",
                        "commands": [
                            {
                                "command": "python -m unittest -v",
                                "returncode": 1,
                                "failure_category": "test-failure",
                                "output_summary": "AssertionError",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {}, clear=True):
                result = run_demo_doctor(fue_public=public)

            self.assertTrue(result.passed)
            rendered = result.to_text()
            self.assertIn("PASS: fue_required_files", rendered)
            self.assertIn("WARN: model", rendered)
            self.assertIn("WARN: public_evidence", rendered)

    def test_required_public_evidence_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            public = Path(tmp) / "public"
            public.mkdir()
            (public / "index.html").write_text("<html>ok</html>", encoding="utf-8")
            (public / "report.md").write_text("# Report\n", encoding="utf-8")
            (public / "public-run.json").write_text('{"commands":[]}', encoding="utf-8")

            missing = run_demo_doctor(fue_public=public, require_evidence=True)
            self.assertFalse(missing.passed)
            self.assertIn("FAIL: public_evidence", missing.to_text())

            evidence = public / "repo" / "reports" / "evidence" / "checkout.png"
            evidence.parent.mkdir(parents=True)
            evidence.write_bytes(b"synthetic-png")
            present = run_demo_doctor(fue_public=public, require_evidence=True)
            self.assertTrue(present.passed)
            self.assertIn("PASS: public_evidence", present.to_text())

    def test_fue_public_fails_when_full_run_json_or_local_paths_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            public = Path(tmp) / "public"
            public.mkdir()
            (public / "index.html").write_text("/data/workspace/t-test-agent/runs/report.html", encoding="utf-8")
            (public / "report.md").write_text("# Report\n", encoding="utf-8")
            (public / "public-run.json").write_text('{"commands":[{"stdout":"full"}]}', encoding="utf-8")
            (public / "run.json").write_text("{}", encoding="utf-8")

            result = run_demo_doctor(fue_public=public, require_detail_url=True)

            self.assertFalse(result.passed)
            rendered = result.to_text()
            self.assertIn("FAIL: detail_url", rendered)
            self.assertIn("FAIL: fue_full_run_json", rendered)
            self.assertIn("FAIL: public_run_json", rendered)
            self.assertIn("local-path", rendered)


if __name__ == "__main__":
    unittest.main()
