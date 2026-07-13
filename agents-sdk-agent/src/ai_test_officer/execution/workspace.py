from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..integrations.gongfeng import MrContext
from ..tools.git import (
    GitDiff,
    GitToolError,
    apply_diff_to_workspace,
    clone_for_run,
    collect_git_diff,
    fetch_workspace_ref,
    read_origin_url,
    resolve_workspace_ref,
    switch_workspace_detached,
)


@dataclass(frozen=True)
class RunWorkspace:
    run_id: str
    run_dir: Path
    repo_dir: Path
    logs_dir: Path
    evidence_dir: Path
    git_diff: GitDiff
    checkout_strategy: str = "local-git-range"
    checkout_status: str = "ready"
    checkout_error: str = ""


def create_run_workspace(
    *,
    source_repo: Path,
    git_range: str,
    runs_root: Path = Path("runs"),
    run_id: str | None = None,
    git_diff: GitDiff | None = None,
    clone_ref: str | None = None,
    apply_diff: bool = False,
) -> RunWorkspace:
    repo = source_repo.expanduser().resolve()
    diff = git_diff or collect_git_diff(repo, git_range)
    resolved_run_id = run_id or _new_run_id()
    run_dir = runs_root.expanduser().resolve() / resolved_run_id
    repo_dir = run_dir / "repo"
    logs_dir = run_dir / "logs"
    evidence_dir = run_dir / "evidence"
    logs_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    clone_for_run(repo, repo_dir, clone_ref if clone_ref is not None else diff.head)
    if apply_diff:
        apply_diff_to_workspace(repo_dir, diff.diff_text)
    return RunWorkspace(resolved_run_id, run_dir, repo_dir, logs_dir, evidence_dir, diff)


def create_mr_run_workspace(
    *,
    source_repo: Path,
    git_range: str,
    git_diff: GitDiff,
    mr_context: MrContext,
    runs_root: Path = Path("runs"),
    run_id: str | None = None,
    checkout_mode: str = "auto",
) -> RunWorkspace:
    repo = source_repo.expanduser().resolve()
    resolved_run_id = run_id or _new_run_id()
    run_dir = runs_root.expanduser().resolve() / resolved_run_id
    repo_dir = run_dir / "repo"
    logs_dir = run_dir / "logs"
    evidence_dir = run_dir / "evidence"
    logs_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    clone_for_run(repo, repo_dir)

    errors: list[str] = []
    remote = read_origin_url(repo) or "origin"
    if checkout_mode not in {"auto", "source-ref", "target-apply-diff", "diff-only"}:
        raise GitToolError(f"unsupported MR checkout mode: {checkout_mode}")
    if checkout_mode == "diff-only":
        return _mr_workspace(
            resolved_run_id,
            run_dir,
            repo_dir,
            logs_dir,
            evidence_dir,
            git_diff,
            strategy="diff-only",
            status="blocked",
            error="MR checkout mode is diff-only; tests were skipped.",
        )

    if checkout_mode in {"auto", "source-ref"}:
        try:
            _checkout_source_ref(repo_dir, remote, mr_context)
            return _mr_workspace(
                resolved_run_id,
                run_dir,
                repo_dir,
                logs_dir,
                evidence_dir,
                git_diff,
                strategy="source-ref",
                status="ready",
            )
        except GitToolError as exc:
            errors.append(f"source-ref: {exc}")
            if checkout_mode == "source-ref":
                return _mr_workspace(
                    resolved_run_id,
                    run_dir,
                    repo_dir,
                    logs_dir,
                    evidence_dir,
                    git_diff,
                    strategy="source-ref",
                    status="blocked",
                    error="; ".join(errors),
                )

    if checkout_mode in {"auto", "target-apply-diff"}:
        try:
            _checkout_target_then_apply_diff(repo_dir, remote, mr_context, git_diff)
            return _mr_workspace(
                resolved_run_id,
                run_dir,
                repo_dir,
                logs_dir,
                evidence_dir,
                git_diff,
                strategy="target-apply-diff",
                status="ready",
            )
        except GitToolError as exc:
            errors.append(f"target-apply-diff: {exc}")
            if checkout_mode == "target-apply-diff":
                return _mr_workspace(
                    resolved_run_id,
                    run_dir,
                    repo_dir,
                    logs_dir,
                    evidence_dir,
                    git_diff,
                    strategy="target-apply-diff",
                    status="blocked",
                    error="; ".join(errors),
                )

    return _mr_workspace(
        resolved_run_id,
        run_dir,
        repo_dir,
        logs_dir,
        evidence_dir,
        git_diff,
        strategy="diff-only",
        status="blocked",
        error="; ".join(errors) or "MR checkout failed.",
    )


def _checkout_source_ref(repo_dir: Path, remote: str, mr_context: MrContext) -> None:
    if not mr_context.source_branch and not mr_context.source_sha:
        raise GitToolError("MR response did not include source branch or source sha")
    if mr_context.source_branch:
        fetch_workspace_ref(repo_dir, remote, _head_ref(mr_context.source_branch))
    if mr_context.source_sha:
        try:
            resolve_workspace_ref(repo_dir, mr_context.source_sha)
        except GitToolError:
            if not mr_context.source_branch:
                fetch_workspace_ref(repo_dir, remote, mr_context.source_sha)
        switch_workspace_detached(repo_dir, mr_context.source_sha)
        return
    switch_workspace_detached(repo_dir, "FETCH_HEAD")


def _checkout_target_then_apply_diff(
    repo_dir: Path,
    remote: str,
    mr_context: MrContext,
    git_diff: GitDiff,
) -> None:
    if mr_context.target_branch:
        fetch_workspace_ref(repo_dir, remote, _head_ref(mr_context.target_branch))
    if mr_context.target_sha:
        try:
            resolve_workspace_ref(repo_dir, mr_context.target_sha)
        except GitToolError:
            if not mr_context.target_branch:
                fetch_workspace_ref(repo_dir, remote, mr_context.target_sha)
        switch_workspace_detached(repo_dir, mr_context.target_sha)
    elif mr_context.target_branch:
        switch_workspace_detached(repo_dir, "FETCH_HEAD")
    else:
        raise GitToolError("MR response did not include target branch or target sha")
    apply_diff_to_workspace(repo_dir, git_diff.diff_text)


def _head_ref(branch_or_ref: str) -> str:
    if branch_or_ref.startswith("refs/"):
        return branch_or_ref
    return f"refs/heads/{branch_or_ref}"


def _mr_workspace(
    run_id: str,
    run_dir: Path,
    repo_dir: Path,
    logs_dir: Path,
    evidence_dir: Path,
    git_diff: GitDiff,
    *,
    strategy: str,
    status: str,
    error: str = "",
) -> RunWorkspace:
    return RunWorkspace(
        run_id,
        run_dir,
        repo_dir,
        logs_dir,
        evidence_dir,
        git_diff,
        checkout_strategy=strategy,
        checkout_status=status,
        checkout_error=error,
    )


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
