from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agent.config import model_provider_from_env
from .config import SECRET_NAMES


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    message: str


@dataclass(frozen=True)
class DemoDoctorResult:
    checks: list[DoctorCheck]

    @property
    def passed(self) -> bool:
        return all(check.status != "fail" for check in self.checks)

    def to_text(self) -> str:
        lines = ["AI Test Officer Demo Doctor"]
        for check in self.checks:
            lines.append(f"- {check.status.upper()}: {check.name}: {check.message}")
        lines.append(f"Passed: {self.passed}")
        return "\n".join(lines)


def run_demo_doctor(
    *,
    fue_public: Path | None = None,
    detail_url: str | None = None,
    require_detail_url: bool = False,
    require_evidence: bool = False,
) -> DemoDoctorResult:
    checks = [
        _model_check(),
        _wecom_check(),
        _detail_url_check(detail_url, require_detail_url=require_detail_url),
    ]
    if fue_public:
        checks.extend(
            _fue_public_checks(
                fue_public.expanduser().resolve(),
                require_evidence=require_evidence,
            )
        )
    else:
        checks.append(DoctorCheck("fue_public", "warn", "not provided; skipping FUE package checks"))
    return DemoDoctorResult(checks)


def _model_check() -> DoctorCheck:
    provider = model_provider_from_env()
    if provider.available:
        return DoctorCheck("model", "pass", f"configured model `{provider.model}`")
    return DoctorCheck("model", "warn", "model key is not configured; deterministic rehearsal still works")


def _wecom_check() -> DoctorCheck:
    if os.getenv("WECOM_WEBHOOK_URL") or os.getenv("WECOM_WEBHOOK_KEY"):
        return DoctorCheck("wecom", "pass", "webhook env is configured")
    return DoctorCheck("wecom", "warn", "webhook env is missing; --send will fail until configured")


def _detail_url_check(detail_url: str | None, *, require_detail_url: bool) -> DoctorCheck:
    if detail_url and detail_url.startswith(("https://", "http://")):
        return DoctorCheck("detail_url", "pass", "clickable report URL provided")
    if require_detail_url:
        return DoctorCheck("detail_url", "fail", "missing clickable report URL")
    return DoctorCheck("detail_url", "warn", "not provided; use --detail-url after FUE deploy")


def _fue_public_checks(public_dir: Path, *, require_evidence: bool) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    if not public_dir.exists() or not public_dir.is_dir():
        return [DoctorCheck("fue_public", "fail", f"directory not found: {public_dir}")]

    required_files = ("index.html", "report.md", "public-run.json")
    missing = [name for name in required_files if not (public_dir / name).is_file()]
    if missing:
        checks.append(DoctorCheck("fue_required_files", "fail", f"missing: {', '.join(missing)}"))
    else:
        checks.append(DoctorCheck("fue_required_files", "pass", "index.html/report.md/public-run.json exist"))

    if (public_dir / "run.json").exists():
        checks.append(DoctorCheck("fue_full_run_json", "fail", "full run.json must not be exported to FUE public"))
    else:
        checks.append(DoctorCheck("fue_full_run_json", "pass", "full run.json is not exported"))

    checks.append(_public_run_json_check(public_dir / "public-run.json"))
    checks.append(_public_content_scan(public_dir))
    checks.append(_evidence_check(public_dir, required=require_evidence))
    return checks


def _evidence_check(public_dir: Path, *, required: bool) -> DoctorCheck:
    evidence = [
        path
        for path in public_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    if evidence:
        return DoctorCheck("public_evidence", "pass", f"found {len(evidence)} image evidence file(s)")
    if required:
        return DoctorCheck("public_evidence", "fail", "required image evidence is missing")
    return DoctorCheck("public_evidence", "warn", "no image evidence found")


def _public_run_json_check(path: Path) -> DoctorCheck:
    if not path.exists():
        return DoctorCheck("public_run_json", "fail", "public-run.json is missing")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return DoctorCheck("public_run_json", "fail", f"invalid JSON: {exc}")
    command_leaks = _find_forbidden_command_keys(data)
    if command_leaks:
        return DoctorCheck("public_run_json", "fail", f"contains non-public command fields: {', '.join(command_leaks)}")
    return DoctorCheck("public_run_json", "pass", "JSON shape is public-safe")


def _find_forbidden_command_keys(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["root"]
    leaks: list[str] = []
    commands = data.get("commands")
    if not isinstance(commands, list):
        return leaks
    for item in commands:
        if not isinstance(item, dict):
            continue
        for key in ("stdout", "stderr"):
            if key in item:
                leaks.append(key)
    return sorted(set(leaks))


def _public_content_scan(public_dir: Path) -> DoctorCheck:
    scanned_files = [
        path
        for path in public_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".html", ".md", ".json", ".txt", ".js", ".css"}
    ]
    violations: list[str] = []
    for path in scanned_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        reason = _content_violation(text)
        if reason:
            violations.append(f"{path.relative_to(public_dir)}:{reason}")
        if len(violations) >= 5:
            break
    if violations:
        return DoctorCheck("public_content_scan", "fail", "; ".join(violations))
    return DoctorCheck("public_content_scan", "pass", f"scanned {len(scanned_files)} public text file(s)")


def _content_violation(text: str) -> str | None:
    if "/data/workspace/" in text or "/root/" in text or "file://" in text:
        return "local-path"
    if "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=" in text:
        return "wecom-webhook"
    for name in SECRET_NAMES:
        if re.search(rf"{re.escape(name)}\s*[:=]\s*[^\s\"']+", text, flags=re.IGNORECASE):
            return name
    if re.search(r"sk-[A-Za-z0-9_\-]{12,}", text):
        return "openai-key"
    return None
