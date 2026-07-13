from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .execution.runner import RunConfig, run_test_officer
from .models import RunRecord
from .redaction import redact_secrets

MR_URL_RE = re.compile(r"https://git\.woa\.com/[^\s)`]+/-/merge_requests/\d+")


@dataclass(frozen=True)
class BatchMrConfig:
    candidate_file: Path
    runs_root: Path
    task: str
    planner_mode: str = "agent"
    memory_mode: str = "structured"
    allow_temp_test_code: bool = False
    max_agent_turns: int = 20
    mr_checkout_mode: str = "auto"
    limit: int | None = None


@dataclass(frozen=True)
class BatchMrItem:
    url: str
    run_id: str


@dataclass(frozen=True)
class BatchMrResult:
    item: BatchMrItem
    status: str
    report_path: Path | None = None
    json_path: Path | None = None
    html_path: Path | None = None
    verdict: str = "blocked"
    risk: str = "high"
    failure_category: str = "batch-error"
    blocked_reason: str = ""
    command_count: int = 0
    checkout_strategy: str = ""
    checkout_status: str = ""
    checkout_error: str = ""
    demo_fit: str = "low"


@dataclass(frozen=True)
class BatchMrSummary:
    runs_root: Path
    results: list[BatchMrResult]

    @property
    def markdown_path(self) -> Path:
        return self.runs_root / "batch-summary.md"

    @property
    def json_path(self) -> Path:
        return self.runs_root / "batch-summary.json"


def parse_mr_urls_from_markdown(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    urls: list[str] = []
    seen: set[str] = set()
    for match in MR_URL_RE.finditer(text):
        url = match.group(0).rstrip(".,")
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def run_mr_batch(config: BatchMrConfig) -> BatchMrSummary:
    urls = parse_mr_urls_from_markdown(config.candidate_file)
    if config.limit is not None:
        urls = urls[: config.limit]
    config.runs_root.mkdir(parents=True, exist_ok=True)
    results: list[BatchMrResult] = []
    for url in urls:
        item = BatchMrItem(url=url, run_id=_run_id_for_mr(url))
        try:
            record = run_test_officer(
                RunConfig(
                    task=config.task,
                    runs_root=config.runs_root,
                    run_id=item.run_id,
                    mr_url=url,
                    planner_mode=config.planner_mode,
                    memory_mode=config.memory_mode,
                    allow_temp_test_code=config.allow_temp_test_code,
                    max_agent_turns=config.max_agent_turns,
                    mr_checkout_mode=config.mr_checkout_mode,
                )
            )
        except Exception as exc:
            results.append(_error_result(item, exc))
            continue
        results.append(_record_result(item, record))

    summary = BatchMrSummary(runs_root=config.runs_root, results=results)
    write_batch_summary(summary)
    return summary


def write_batch_summary(summary: BatchMrSummary) -> None:
    summary.runs_root.mkdir(parents=True, exist_ok=True)
    summary.json_path.write_text(_summary_json(summary), encoding="utf-8")
    summary.markdown_path.write_text(_summary_markdown(summary), encoding="utf-8")


def _run_id_for_mr(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    project, iid = path.split("/-/merge_requests/", 1)
    service = project.rsplit("/", 1)[-1]
    iid = iid.strip("/").split("/", 1)[0]
    safe_service = re.sub(r"[^A-Za-z0-9_.-]+", "-", service).strip("-")
    return f"{safe_service}-{iid}"


def _record_result(item: BatchMrItem, record: RunRecord) -> BatchMrResult:
    return BatchMrResult(
        item=item,
        status="ok",
        report_path=record.report_path,
        json_path=record.json_path,
        html_path=record.html_path,
        verdict=record.verdict,
        risk=record.risk,
        failure_category=record.failure_category,
        blocked_reason=record.blocked_reason,
        command_count=len(record.commands),
        checkout_strategy=record.checkout_strategy,
        checkout_status=record.checkout_status,
        checkout_error=record.checkout_error,
        demo_fit=_demo_fit(record),
    )


def _error_result(item: BatchMrItem, exc: Exception) -> BatchMrResult:
    return BatchMrResult(
        item=item,
        status="error",
        blocked_reason=redact_secrets(str(exc))[:1000],
        checkout_status="error",
        checkout_error=redact_secrets(str(exc))[:1000],
    )


def _summary_json(summary: BatchMrSummary) -> str:
    data = {
        "runs_root": str(summary.runs_root),
        "total": len(summary.results),
        "ok": sum(1 for item in summary.results if item.status == "ok"),
        "error": sum(1 for item in summary.results if item.status == "error"),
        "results": [
            {
                "url": item.item.url,
                "run_id": item.item.run_id,
                "status": item.status,
                "report_path": str(item.report_path) if item.report_path else None,
                "json_path": str(item.json_path) if item.json_path else None,
                "html_path": str(item.html_path) if item.html_path else None,
                "verdict": item.verdict,
                "risk": item.risk,
                "failure_category": item.failure_category,
                "blocked_reason": item.blocked_reason,
                "command_count": item.command_count,
                "checkout_strategy": item.checkout_strategy,
                "checkout_status": item.checkout_status,
                "checkout_error": item.checkout_error,
                "demo_fit": item.demo_fit,
            }
            for item in summary.results
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def _summary_markdown(summary: BatchMrSummary) -> str:
    lines = [
        "# Real MR Batch Summary",
        "",
        f"- Total: {len(summary.results)}",
        f"- OK: {sum(1 for item in summary.results if item.status == 'ok')}",
        f"- Error: {sum(1 for item in summary.results if item.status == 'error')}",
        "",
        "| MR | Status | Checkout | Demo Fit | Verdict | Risk | Category | Commands | Report | Note |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for result in summary.results:
        report = str(result.report_path) if result.report_path else ""
        note = (result.blocked_reason or "").replace("\n", " ").replace("|", "\\|")[:180]
        lines.append(
            "| "
            + " | ".join(
                [
                    result.item.url,
                    result.status,
                    f"{result.checkout_strategy or '-'}:{result.checkout_status or '-'}",
                    result.demo_fit,
                    result.verdict,
                    result.risk,
                    result.failure_category,
                    str(result.command_count),
                    report,
                    note,
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _demo_fit(record: RunRecord) -> str:
    if record.checkout_status != "ready":
        return "low"
    if record.verdict == "fail" and record.commands:
        return "high"
    if record.verdict == "pass" and 1 <= len(record.commands) <= 8:
        return "high"
    if record.verdict in {"pass", "blocked"} and record.commands:
        return "medium"
    return "low"
