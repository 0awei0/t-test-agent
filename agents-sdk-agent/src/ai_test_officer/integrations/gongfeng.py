from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from ..config import DEFAULT_REPO_ROOTS
from ..models import ChangedFile
from ..tools.git import GitDiff
from ..redaction import redact_secrets

GONGFENG_API_BASE = "https://git.woa.com/api/v3"


class GongfengError(RuntimeError):
    """Raised when a Gongfeng read-only request fails."""


@dataclass(frozen=True)
class ParsedMrUrl:
    project_path: str
    iid: int

    @property
    def project_api_id(self) -> str:
        return urllib.parse.quote(self.project_path, safe="")


@dataclass(frozen=True)
class MrFileChange:
    status: str
    old_path: str
    new_path: str
    diff: str
    additions: int
    deletions: int

    @property
    def path(self) -> str:
        return self.new_path if self.new_path != "/dev/null" else self.old_path


@dataclass(frozen=True)
class MrContext:
    url: str
    project_path: str
    iid: int
    id: int
    title: str
    state: str
    source_branch: str
    target_branch: str
    source_sha: str | None
    target_sha: str | None
    files: list[MrFileChange]

    @property
    def changed_files(self) -> list[ChangedFile]:
        return [ChangedFile(item.status, item.path) for item in self.files]


def parse_mr_url(url: str) -> ParsedMrUrl:
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc != "git.woa.com":
        raise GongfengError("MR URL must use git.woa.com")
    marker = "/-/merge_requests/"
    if marker not in parsed.path:
        raise GongfengError("MR URL must contain /-/merge_requests/<iid>")
    project_path, iid_text = parsed.path.split(marker, 1)
    project_path = project_path.strip("/")
    iid_part = iid_text.strip("/").split("/", 1)[0]
    if not project_path or not iid_part.isdigit():
        raise GongfengError("MR URL project path or iid is invalid")
    return ParsedMrUrl(project_path, int(iid_part))


def fetch_mr_context(url: str, *, token: str | None = None) -> MrContext:
    parsed = parse_mr_url(url)
    resolved_token = token or os.getenv("GONGFENG_ACCESS_TOKEN")
    if not resolved_token:
        raise GongfengError("missing GONGFENG_ACCESS_TOKEN")

    mr = _get_json(
        f"/projects/{parsed.project_api_id}/merge_request/iid/{parsed.iid}",
        token=resolved_token,
    )
    mr_id = int(mr["id"])
    changes = _get_json(
        f"/projects/{parsed.project_api_id}/merge_request/{mr_id}/changes",
        token=resolved_token,
    )
    files = [_parse_file_change(item) for item in changes.get("files", [])]
    return MrContext(
        url=url,
        project_path=parsed.project_path,
        iid=parsed.iid,
        id=mr_id,
        title=str(mr.get("title") or ""),
        state=str(mr.get("state") or ""),
        source_branch=str(mr.get("source_branch") or ""),
        target_branch=str(mr.get("target_branch") or ""),
        source_sha=_optional_str(mr.get("source_branch_sha") or mr.get("sha")),
        target_sha=_optional_str(mr.get("target_branch_sha")),
        files=files,
    )


def resolve_local_repo_for_mr(project_path: str, explicit_repo: Path | None = None) -> Path:
    if explicit_repo is not None:
        return explicit_repo.expanduser().resolve()

    relative = Path(*project_path.split("/"))
    candidates: list[Path] = []
    roots_env = os.getenv("AI_TEST_OFFICER_REPO_ROOTS")
    if roots_env:
        roots = tuple(Path(item) for item in roots_env.split(os.pathsep) if item)
    else:
        roots = DEFAULT_REPO_ROOTS
    for root in roots:
        candidates.append(root / relative.name)
        candidates.append(root / relative)
    for candidate in candidates:
        if (candidate / ".git").exists():
            return candidate.resolve()
    raise GongfengError(
        "could not find a local checkout for MR project; pass --repo or set AI_TEST_OFFICER_REPO_ROOTS"
    )


def mr_git_range(context: MrContext) -> str:
    if context.target_branch and context.source_branch:
        return f"{context.target_branch}..{context.source_branch}"
    if context.target_sha and context.source_sha:
        return f"{context.target_sha}..{context.source_sha}"
    raise GongfengError("MR response did not include usable source/target refs")


def mr_git_diff(context: MrContext) -> GitDiff:
    range_spec = mr_git_range(context)
    base, head = range_spec.split("..", 1)
    diff_text = "\n".join(item.diff.rstrip("\n") for item in context.files if item.diff).strip()
    if not diff_text:
        raise GongfengError("MR response did not include file diffs")
    return GitDiff(
        range_spec=range_spec,
        base=base,
        head=head,
        diff_text=diff_text + "\n",
        changed_files=context.changed_files,
    )


def _get_json(path: str, *, token: str) -> dict[str, object]:
    request = urllib.request.Request(
        f"{GONGFENG_API_BASE}{path}",
        headers={"PRIVATE-TOKEN": token},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise GongfengError(redact_secrets(str(exc))) from exc


def _parse_file_change(item: dict[str, object]) -> MrFileChange:
    old_path = str(item.get("old_path") or "/dev/null")
    new_path = str(item.get("new_path") or old_path)
    diff = str(item.get("diff") or "")
    additions = sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
    status = _status(old_path, new_path)
    return MrFileChange(status, old_path, new_path, diff, additions, deletions)


def _status(old_path: str, new_path: str) -> str:
    if old_path == "/dev/null":
        return "A"
    if new_path == "/dev/null":
        return "D"
    if old_path != new_path:
        return "R"
    return "M"


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None
