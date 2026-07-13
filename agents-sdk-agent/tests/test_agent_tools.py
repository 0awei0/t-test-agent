import tempfile
import unittest
from pathlib import Path

from ai_test_officer.models import ChangedFile
from ai_test_officer.tools import AgentRunTools, LocalTestTools


class AgentToolsTests(unittest.TestCase):
    def test_read_file_diff_and_temp_write_are_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            context = root / "context"
            logs = root / "logs"
            repo.mkdir()
            context.mkdir()
            logs.mkdir()
            (context / "diffs").mkdir()
            (context / "diffs" / "a.diff").write_text("+change\n", encoding="utf-8")
            (context / "diff-index.json").write_text(
                '[{"path":"a.py","artifact":"diffs/a.diff"}]',
                encoding="utf-8",
            )
            local = LocalTestTools(repo, logs, allow_temp_test_code=True)
            tools = AgentRunTools(local, [ChangedFile("M", "a.py")], context, [], [])

            self.assertIn("+change", tools.read_file_diff("a.py"))
            generated = tools.write_temp_test("tests/test_generated.py", "def test_x(): pass\n")

            self.assertTrue(generated.path.exists())
            self.assertTrue((repo / "tests" / "test_generated.py").exists())


if __name__ == "__main__":
    unittest.main()
