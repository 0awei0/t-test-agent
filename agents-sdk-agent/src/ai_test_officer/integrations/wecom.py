from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from ..models import RunRecord
from ..redaction import redact_secrets


class NotifyError(RuntimeError):
    """Raised when outbound notification cannot be delivered."""


@dataclass(frozen=True)
class NotifyResult:
    delivered: bool
    dry_run: bool
    status: int | None
    body: str


def build_wecom_markdown(record: RunRecord) -> str:
    scenario = _scenario_label(record)
    changed = ", ".join(item.path for item in record.changed_files[:5]) or "无"
    if len(record.changed_files) > 5:
        changed += f", +{len(record.changed_files) - 5} more"
    generated = "是" if record.generated_files else "否"
    color = "warning" if record.verdict == "fail" else "info"
    if record.detail_url:
        return (
            "**AI 测试官**\n"
            f"> 场景: `{scenario}`\n"
            f"> 结论: <font color=\"{color}\">{record.verdict}</font>\n"
            f"> 风险: `{record.risk}`\n"
            f"> 变更: `{changed}`\n"
            f"> 结果: {record.summary}\n"
            f"> [查看完整测试报告]({record.detail_url})"
        )
    return (
        "**AI 测试官**\n"
        f"> 场景: `{scenario}`\n"
        f"> 运行: `{record.run_id}`\n"
        f"> 结论: <font color=\"{color}\">{record.verdict}</font>\n"
        f"> 风险: `{record.risk}`\n"
        f"> 变更: `{changed}`\n"
        f"> 临时测试: `{generated}`\n"
        f"> 摘要: {record.summary}\n"
        f"> 报告: `runs/{record.run_id}/report.md`"
    )


def send_wecom_markdown(markdown: str, *, webhook_url: str | None = None, dry_run: bool = False) -> NotifyResult:
    url = webhook_url or _resolve_wecom_webhook_url()
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": redact_secrets(markdown),
        },
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if dry_run:
        return NotifyResult(delivered=False, dry_run=True, status=None, body=body.decode("utf-8"))
    if not url:
        raise NotifyError("missing WECOM_WEBHOOK_URL or WECOM_WEBHOOK_KEY")

    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            status = response.status
    except urllib.error.URLError as exc:
        raise NotifyError(f"WeCom webhook request failed: {exc}") from exc

    redacted_body = redact_secrets(response_body)
    try:
        parsed = json.loads(response_body)
    except json.JSONDecodeError:
        parsed = {}
    if status >= 400 or parsed.get("errcode") not in {None, 0}:
        raise NotifyError(f"WeCom webhook returned status={status}, body={redacted_body}")
    return NotifyResult(delivered=True, dry_run=False, status=status, body=redacted_body)


def _resolve_wecom_webhook_url() -> str | None:
    url = os.getenv("WECOM_WEBHOOK_URL")
    if url:
        return url
    key = os.getenv("WECOM_WEBHOOK_KEY")
    if key:
        return f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
    return None


def _scenario_label(record: RunRecord) -> str:
    if record.mr_project and record.mr_iid:
        return f"{record.mr_project}!{record.mr_iid}"
    text = f"{record.run_id} {record.task}".lower()
    if "agent-loop" in text:
        return "agent-loop"
    if "fullstack" in text:
        return "fullstack"
    return "local-change"
