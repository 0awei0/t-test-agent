import json
import tempfile
import unittest
from pathlib import Path

from ai_test_officer.context import build_context_artifacts
from ai_test_officer.integrations.gongfeng import MrContext, MrFileChange
from ai_test_officer.models import RunRecord
from ai_test_officer.report import write_outputs


class ContextTests(unittest.TestCase):
    def test_builds_mr_context_artifacts_without_raw_diff_in_run_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            mr = MrContext(
                url="https://git.woa.com/example/project/-/merge_requests/10",
                project_path="example/project",
                iid=10,
                id=123,
                title="MR title",
                state="opened",
                source_branch="feature",
                target_branch="master",
                source_sha=None,
                target_sha=None,
                files=[MrFileChange("A", "/dev/null", "tests/example.spec.ts", "+secret diff\n", 1, 0)],
            )
            artifacts = build_context_artifacts(
                run_dir=run_dir,
                changed_files=mr.changed_files,
                diff_text="x" * 40_000,
                mr_context=mr,
            )
            record = RunRecord(
                run_id="run",
                task="Analyze",
                source_repo=Path("/source"),
                workspace_repo=Path("/workspace"),
                run_dir=run_dir,
                git_range="master..feature",
                changed_files=mr.changed_files,
                diff_text="x" * 40_000,
                allow_temp_test_code=False,
                mr_url=mr.url,
                mr_project=mr.project_path,
                mr_iid=mr.iid,
                mr_title=mr.title,
                context_strategy=artifacts.strategy,
                context_summary=artifacts.summary,
                context_dir=artifacts.context_dir,
                diff_index_path=artifacts.diff_index_path,
            )

            write_outputs(record)
            run_json = json.loads(record.json_path.read_text(encoding="utf-8"))

            self.assertEqual(artifacts.strategy, "indexed-summary")
            self.assertTrue((run_dir / "context" / "mr.json").exists())
            self.assertTrue((run_dir / "context" / "diff-index.json").exists())
            self.assertIsNone(run_json["diff_text"])
            self.assertIn("tests/example.spec.ts", artifacts.summary)


if __name__ == "__main__":
    unittest.main()
