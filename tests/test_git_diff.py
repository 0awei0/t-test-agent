import subprocess
import tempfile
import unittest
from pathlib import Path

from ai_test_officer.git_diff import (
    GitDiffError,
    collect_git_range_diff,
    collect_last_commit_diff,
    parse_git_range,
)


class GitDiffTests(unittest.TestCase):
    def test_parse_git_range_requires_base_and_head(self) -> None:
        self.assertEqual(parse_git_range("main..feature"), ("main", "feature"))

        with self.assertRaises(GitDiffError):
            parse_git_range("main...feature")
        with self.assertRaises(GitDiffError):
            parse_git_range("main")

    def test_collect_last_commit_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(Path(tmp))

            diff = collect_last_commit_diff(repo)

            self.assertEqual(diff.label, "HEAD~1..HEAD")
            self.assertIn("checkout.py", diff.name_status)
            self.assertIn("+    return value + 2", diff.diff)

    def test_collect_git_range_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(Path(tmp))
            base = _git(repo, "rev-parse", "HEAD~1").strip()
            head = _git(repo, "rev-parse", "HEAD").strip()

            diff = collect_git_range_diff(repo, f"{base}..{head}")

            self.assertEqual(diff.label, f"{base}..{head}")
            self.assertIn("M\tcheckout.py", diff.name_status)

    def test_empty_range_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(Path(tmp))

            with self.assertRaises(GitDiffError):
                collect_git_range_diff(repo, "HEAD..HEAD")


def _make_repo(repo: Path) -> Path:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")

    (repo / "checkout.py").write_text("def adjust(value):\n    return value + 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")

    (repo / "checkout.py").write_text("def adjust(value):\n    return value + 2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "change checkout")
    return repo


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


if __name__ == "__main__":
    unittest.main()
