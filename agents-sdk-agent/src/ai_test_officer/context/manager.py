from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from ..config import CONTEXT_DIRECT_DIFF_MAX_CHARS
from ..integrations.gongfeng import MrContext
from ..models import ChangedFile
from ..redaction import redact_secrets


@dataclass(frozen=True)
class DiffFileIndex:
    path: str
    status: str
    additions: int
    deletions: int
    diff_chars: int
    artifact: str


@dataclass(frozen=True)
class ContextArtifacts:
    context_dir: Path
    summary_path: Path
    diff_index_path: Path
    changed_files_path: Path
    mr_path: Path | None
    diff_index: list[DiffFileIndex]
    summary: str
    strategy: str


def build_context_artifacts(
    *,
    run_dir: Path,
    changed_files: list[ChangedFile],
    diff_text: str,
    mr_context: MrContext | None = None,
) -> ContextArtifacts:
    context_dir = run_dir / "context"
    diffs_dir = context_dir / "diffs"
    diffs_dir.mkdir(parents=True, exist_ok=True)
    changed_files_path = context_dir / "changed-files.json"
    diff_index_path = context_dir / "diff-index.json"
    summary_path = context_dir / "context_summary.md"
    mr_path = context_dir / "mr.json" if mr_context else None

    if mr_context:
        mr_path.write_text(
            json.dumps(_mr_json(mr_context), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if mr_context and _same_changed_paths(changed_files, mr_context):
        index = _write_mr_diffs(context_dir, diffs_dir, mr_context)
    else:
        index = _write_unified_diffs(diffs_dir, changed_files, diff_text)

    changed_files_path.write_text(
        json.dumps([asdict(item) for item in changed_files], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    diff_index_path.write_text(
        json.dumps([asdict(item) for item in index], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    strategy = "direct" if len(diff_text) <= CONTEXT_DIRECT_DIFF_MAX_CHARS else "indexed-summary"
    summary = _render_summary(index=index, changed_files=changed_files, mr_context=mr_context, strategy=strategy)
    summary_path.write_text(summary, encoding="utf-8")
    return ContextArtifacts(
        context_dir=context_dir,
        summary_path=summary_path,
        diff_index_path=diff_index_path,
        changed_files_path=changed_files_path,
        mr_path=mr_path,
        diff_index=index,
        summary=summary,
        strategy=strategy,
    )


def _write_mr_diffs(context_dir: Path, diffs_dir: Path, mr_context: MrContext) -> list[DiffFileIndex]:
    index: list[DiffFileIndex] = []
    for item in mr_context.files:
        artifact = _artifact_name(item.path)
        artifact_path = diffs_dir / artifact
        artifact_path.write_text(redact_secrets(item.diff), encoding="utf-8")
        index.append(
            DiffFileIndex(
                path=item.path,
                status=item.status,
                additions=item.additions,
                deletions=item.deletions,
                diff_chars=len(item.diff),
                artifact=str(artifact_path.relative_to(context_dir)),
            )
        )
    return index


def _same_changed_paths(changed_files: list[ChangedFile], mr_context: MrContext) -> bool:
    local = sorted(item.path for item in changed_files)
    remote = sorted(item.path for item in mr_context.files)
    return local == remote


def _write_unified_diffs(
    diffs_dir: Path,
    changed_files: list[ChangedFile],
    diff_text: str,
) -> list[DiffFileIndex]:
    sections = _split_unified_diff(diff_text)
    index: list[DiffFileIndex] = []
    for changed in changed_files:
        section = sections.get(changed.path, "")
        artifact = _artifact_name(changed.path)
        artifact_path = diffs_dir / artifact
        artifact_path.write_text(redact_secrets(section), encoding="utf-8")
        additions = sum(1 for line in section.splitlines() if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in section.splitlines() if line.startswith("-") and not line.startswith("---"))
        index.append(
            DiffFileIndex(
                path=changed.path,
                status=changed.status,
                additions=additions,
                deletions=deletions,
                diff_chars=len(section),
                artifact=str(artifact_path.relative_to(diffs_dir.parent)),
            )
        )
    if not index and diff_text:
        artifact_path = diffs_dir / "full.diff"
        artifact_path.write_text(redact_secrets(diff_text), encoding="utf-8")
    return index


def _split_unified_diff(diff_text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    current_path: str | None = None
    current_lines: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            if current_path is not None:
                result[current_path] = "\n".join(current_lines) + "\n"
            current_path = _path_from_diff_header(line)
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_path is not None:
        result[current_path] = "\n".join(current_lines) + "\n"
    return result


def _path_from_diff_header(line: str) -> str:
    parts = line.split()
    if len(parts) >= 4:
        return parts[3].removeprefix("b/")
    return "unknown.diff"


def _render_summary(
    *,
    index: list[DiffFileIndex],
    changed_files: list[ChangedFile],
    mr_context: MrContext | None,
    strategy: str,
) -> str:
    lines = ["# Context Summary", "", f"- Strategy: {strategy}"]
    if mr_context:
        lines.extend(
            [
                f"- MR: {mr_context.project_path}!{mr_context.iid}",
                f"- Title: {mr_context.title}",
                f"- Source: {mr_context.source_branch}",
                f"- Target: {mr_context.target_branch}",
            ]
        )
    lines.extend(["", "## Changed Files"])
    for item in index:
        risk = _risk_hint(item.path)
        lines.append(
            f"- {item.status} {item.path} (+{item.additions}/-{item.deletions}, "
            f"{item.diff_chars} chars, {risk}, diff: `{item.artifact}`)"
        )
    if not index:
        for item in changed_files:
            lines.append(f"- {item.status} {item.path}")
    return "\n".join(lines) + "\n"


def _risk_hint(path: str) -> str:
    lower = path.lower()
    if "test" in lower or lower.endswith(".spec.ts"):
        return "test-surface"
    if "playwright" in lower or "e2e" in lower:
        return "browser-e2e"
    if lower.endswith((".yml", ".yaml")) or "ci" in lower:
        return "ci-config"
    if lower.endswith((".ts", ".js", ".rs", ".go", ".py")):
        return "source"
    return "supporting"


def _artifact_name(path: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "__", path.strip("/"))
    return f"{safe or 'unknown'}.diff"


def _mr_json(mr_context: MrContext) -> dict[str, object]:
    return {
        "url": mr_context.url,
        "project_path": mr_context.project_path,
        "iid": mr_context.iid,
        "id": mr_context.id,
        "title": mr_context.title,
        "state": mr_context.state,
        "source_branch": mr_context.source_branch,
        "target_branch": mr_context.target_branch,
        "source_sha": mr_context.source_sha,
        "target_sha": mr_context.target_sha,
    }
