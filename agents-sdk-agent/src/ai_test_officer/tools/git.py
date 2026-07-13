from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..models import ChangedFile


class GitToolError(RuntimeError):
    """Raised when a read-only git operation fails."""


@dataclass(frozen=True)
class GitDiff:
    range_spec: str
    base: str
    head: str
    diff_text: str
    changed_files: list[ChangedFile]


def parse_git_range(range_spec: str) -> tuple[str, str]:
    if ".." not in range_spec or "..." in range_spec:
        raise GitToolError("git range must use the form `<base>..<head>`")
    base, head = range_spec.split("..", 1)
    if not base or not head:
        raise GitToolError("git range must include both base and head")
    return base, head


def collect_git_diff(repo_path: Path, range_spec: str) -> GitDiff:
    base, head = parse_git_range(range_spec)
    diff_text = run_git(repo_path, ["diff", "--find-renames", base, head])
    if not diff_text.strip():
        raise GitToolError(f"git diff is empty for range `{range_spec}`")
    name_status = run_git(repo_path, ["diff", "--name-status", "--find-renames", base, head])
    changed = _parse_name_status(name_status)
    return GitDiff(range_spec, base, head, diff_text, changed)


def clone_for_run(source_repo: Path, target_repo: Path, head: str | None = None) -> None:
    target_repo.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["git", "clone", "--no-hardlinks", str(source_repo), str(target_repo)],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise GitToolError(_detail(proc))
    if head:
        proc = subprocess.run(
            ["git", "-C", str(target_repo), "switch", "--detach", "--no-guess", "--", head],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise GitToolError(_detail(proc))


def apply_diff_to_workspace(repo_path: Path, diff_text: str) -> None:
    proc = subprocess.run(
        ["git", "-C", str(repo_path), "apply", "--whitespace=nowarn"],
        input=diff_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise GitToolError(_detail(proc))


def fetch_workspace_ref(repo_path: Path, remote: str, ref: str) -> None:
    proc = subprocess.run(
        ["git", "-C", str(repo_path), "fetch", "--no-tags", remote, ref],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise GitToolError(_detail(proc))


def switch_workspace_detached(repo_path: Path, ref: str) -> None:
    proc = subprocess.run(
        ["git", "-C", str(repo_path), "switch", "--detach", "--no-guess", "--", ref],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise GitToolError(_detail(proc))


def resolve_workspace_ref(repo_path: Path, ref: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--verify", ref],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise GitToolError(_detail(proc))
    return proc.stdout.strip()


def read_origin_url(source_repo: Path) -> str | None:
    try:
        value = run_git(source_repo, ["config", "--get", "remote.origin.url"]).strip()
    except GitToolError:
        return None
    return value if value else None


def run_git(repo_path: Path, args: list[str]) -> str:
    if args and args[0] not in {"config", "diff", "show", "log", "status", "rev-parse"}:
        raise GitToolError(f"git subcommand is not allowed on source repo: {args[0]}")
    proc = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise GitToolError(_detail(proc))
    return proc.stdout


def _parse_name_status(text: str) -> list[ChangedFile]:
    changed: list[ChangedFile] = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            changed.append(ChangedFile(status=parts[0], path=parts[-1]))
    return changed


def _detail(proc: subprocess.CompletedProcess[str]) -> str:
    return (proc.stderr or proc.stdout or f"git exited {proc.returncode}").strip()
