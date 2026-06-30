from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitDiffError(RuntimeError):
    """Raised when local git diff input cannot be collected."""


@dataclass(frozen=True)
class LocalGitDiff:
    """Local git diff and changed-file summary for one comparison."""

    label: str
    diff: str
    name_status: str


def collect_last_commit_diff(repo_path: Path) -> LocalGitDiff:
    return collect_git_range_diff(repo_path, "HEAD~1..HEAD")


def collect_git_range_diff(repo_path: Path, range_spec: str) -> LocalGitDiff:
    base, head = parse_git_range(range_spec)
    repo = repo_path.expanduser().resolve()
    _ensure_git_repo(repo)

    diff = _run_git(repo, ["diff", "--find-renames", base, head])
    if not diff.strip():
        raise GitDiffError(f"git diff is empty for range `{range_spec}`; confirm the range.")

    name_status = _run_git(repo, ["diff", "--name-status", "--find-renames", base, head])
    return LocalGitDiff(label=f"{base}..{head}", diff=diff, name_status=name_status)


def parse_git_range(range_spec: str) -> tuple[str, str]:
    if "..." in range_spec or range_spec.count("..") != 1:
        raise GitDiffError("git range must use the form `<base>..<head>`.")

    base, head = (part.strip() for part in range_spec.split("..", 1))
    if not base or not head:
        raise GitDiffError("git range must include both base and head revisions.")
    return base, head


def _ensure_git_repo(repo: Path) -> None:
    if not repo.exists():
        raise GitDiffError(f"repository path does not exist: {repo}")
    output = _run_git(repo, ["rev-parse", "--is-inside-work-tree"]).strip()
    if output != "true":
        raise GitDiffError(f"path is not inside a git work tree: {repo}")


def _run_git(repo: Path, args: list[str]) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip() or f"git exited {proc.returncode}"
        raise GitDiffError(detail)
    return proc.stdout
