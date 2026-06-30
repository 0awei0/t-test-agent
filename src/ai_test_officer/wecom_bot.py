from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_WECOM_WEBHOOK_BASE_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"
MAX_WECOM_MARKDOWN_CHARS = 3500
MAX_WECOM_REPORT_PREVIEW_CHARS = 1800
REPORT_PREVIEW_STOP_HEADINGS = {
    "## Prompt Preview",
    "# Prompt Preview",
    "Prompt Preview",
}
REPORT_PREVIEW_SECTION_ORDER = (
    "## Summary",
    "## Changed Files / Risk Map",
    "## Execution",
    "## Findings",
    "## Recommended Next Steps",
)
SECTION_PREVIEW_CHARS = {
    "## Summary": 650,
    "## Changed Files / Risk Map": 450,
    "## Execution": 450,
    "## Findings": 600,
    "## Recommended Next Steps": 450,
}
PREVIEW_TRUNCATION_SUFFIX = "\n...更多内容见完整报告。"


@dataclass(frozen=True)
class WeComSendResult:
    ok: bool
    status: int | None
    errcode: int | None
    errmsg: str


@dataclass(frozen=True)
class WeComWebhook:
    base_url: str
    key: str

    @property
    def redacted_target(self) -> str:
        return f"{self.base_url}?key=<redacted>"


def resolve_wecom_webhook(webhook_url: str | None, webhook_key: str | None) -> WeComWebhook | None:
    if webhook_url:
        return _parse_webhook_url(webhook_url)
    if webhook_key:
        return WeComWebhook(DEFAULT_WECOM_WEBHOOK_BASE_URL, webhook_key)
    return None


def build_notification_content(
    *,
    message: str | None,
    report_path: Path | None,
    title: str = "AI Test Officer",
) -> str:
    parts = [f"**{title}**"]
    if message:
        parts.append(message.strip())

    if report_path:
        resolved = report_path.expanduser()
        report = resolved.read_text(encoding="utf-8", errors="replace")
        parts.append(f"Report: `{resolved}`")
        parts.append("Preview:")
        parts.append(_report_preview(report))

    return _truncate("\n\n".join(part for part in parts if part), MAX_WECOM_MARKDOWN_CHARS)


def build_wecom_payload(content: str, msgtype: str = "markdown") -> dict[str, Any]:
    if msgtype == "text":
        return {"msgtype": "text", "text": {"content": content}}
    if msgtype == "markdown":
        return {"msgtype": "markdown", "markdown": {"content": content}}
    raise ValueError(f"Unsupported WeCom msgtype: {msgtype}")


def render_dry_run(payload: dict[str, Any], webhook: WeComWebhook | None) -> str:
    target = redacted_webhook_target(webhook)
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return f"""# WeCom Bot Notification

- Mode: dry-run
- Target: {target}
- Sent: false

```json
{body}
```
"""


def redacted_webhook_target(webhook: WeComWebhook | None) -> str:
    if webhook:
        return webhook.redacted_target
    return f"{DEFAULT_WECOM_WEBHOOK_BASE_URL}?key=<not-set>"


def send_wecom_payload(
    webhook_key: str,
    payload: dict[str, Any],
    *,
    timeout: float = 10.0,
    base_url: str = DEFAULT_WECOM_WEBHOOK_BASE_URL,
) -> WeComSendResult:
    url = f"{base_url}?key={urllib.parse.quote(webhook_key, safe='')}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            raw_body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return WeComSendResult(False, exc.code, None, f"HTTP {exc.code}: {exc.reason}")
    except (OSError, urllib.error.URLError) as exc:
        return WeComSendResult(False, None, None, exc.__class__.__name__)

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        return WeComSendResult(False, status, None, "response was not JSON")

    errcode = body.get("errcode")
    errmsg = str(body.get("errmsg", ""))
    return WeComSendResult(errcode == 0, status, errcode, errmsg)


def _parse_webhook_url(webhook_url: str) -> WeComWebhook:
    parsed = urllib.parse.urlparse(webhook_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("WECOM_WEBHOOK_URL must be a full URL")

    key_values = urllib.parse.parse_qs(parsed.query).get("key", [])
    key = key_values[0] if key_values else ""
    if not key:
        raise ValueError("WECOM_WEBHOOK_URL must contain a key query parameter")

    base_url = urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, "", "", "")
    )
    return WeComWebhook(base_url=base_url, key=key)


def _report_preview(report: str, max_chars: int = MAX_WECOM_REPORT_PREVIEW_CHARS) -> str:
    if _is_dry_run_report(report):
        return "Dry-run report was generated locally. Run without `--dry-run` to produce an executable test report."

    title, sections = _parse_report_sections(report)
    preview_lines = [title] if title else []
    for heading in REPORT_PREVIEW_SECTION_ORDER:
        body = sections.get(heading)
        if not body:
            continue
        preview_lines.append(heading)
        preview_lines.append(
            _truncate(body, SECTION_PREVIEW_CHARS[heading], suffix=PREVIEW_TRUNCATION_SUFFIX)
        )

    if not preview_lines:
        preview_lines = _plain_report_lines(report)

    return _truncate("\n".join(preview_lines), max_chars, suffix=PREVIEW_TRUNCATION_SUFFIX)


def _parse_report_sections(report: str) -> tuple[str, dict[str, str]]:
    title = ""
    sections: dict[str, list[str]] = {}
    current_heading = ""
    for line in _plain_report_lines(report):
        stripped = line.strip()
        if stripped.startswith("# ") and not title:
            title = stripped
            continue
        if stripped.startswith("## "):
            current_heading = stripped
            sections.setdefault(current_heading, [])
            continue
        if current_heading:
            sections[current_heading].append(line)

    return title, {
        heading: "\n".join(line for line in lines if line.strip())
        for heading, lines in sections.items()
    }


def _plain_report_lines(report: str) -> list[str]:
    lines: list[str] = []
    for line in report.splitlines():
        stripped = line.strip()
        if stripped in REPORT_PREVIEW_STOP_HEADINGS:
            break
        if stripped and not stripped.startswith("<!--"):
            lines.append(line)
    return lines


def _is_dry_run_report(report: str) -> bool:
    return "<!-- mode: dry-run -->" in report


def _truncate(text: str, max_chars: int, *, suffix: str = PREVIEW_TRUNCATION_SUFFIX) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - len(suffix)].rstrip()}{suffix}"
