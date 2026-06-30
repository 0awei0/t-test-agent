from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


DEFAULT_TAPD_MCP_URL = "https://mcpgw.knot.woa.com/tapd/"
DEFAULT_IWIKI_MCP_URL = "https://prod.mcp.it.woa.com/app_iwiki_mcp/mcp3"
DEFAULT_GONGFENG_API_URL = "https://git.woa.com/api/v3/user"
DEFAULT_TGIT_MCP_PACKAGE = "@tencent/tgit-mcp-server@latest"
DEFAULT_PLAYWRIGHT_MCP_PACKAGE = "@playwright/mcp@latest"

SECRET_KEYS = {
    "TAPD_ACCESS_TOKEN",
    "GONGFENG_ACCESS_TOKEN",
    "TAI_PAT_TOKEN",
    "IWIKI_MCP_TOKEN",
    "WECOM_WEBHOOK_URL",
    "WECOM_WEBHOOK_KEY",
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"


def load_env(path: Path, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Load dotenv-style values without expanding or printing secrets."""

    values = dict(base or os.environ)
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def run_checks(env_path: Path = Path(".env"), timeout: float = 10.0) -> list[CheckResult]:
    env = load_env(env_path)
    return [
        check_tapd(env, timeout),
        check_iwiki(env, timeout),
        check_gongfeng_rest(env, timeout),
        check_tgit_mcp(env, timeout),
        check_playwright_mcp(env, timeout),
        check_playwright_browser(env, timeout),
    ]


def check_tapd(env: Mapping[str, str], timeout: float) -> CheckResult:
    token = env.get("TAPD_ACCESS_TOKEN", "")
    if not token:
        return CheckResult("TAPD MCP", False, "TAPD_ACCESS_TOKEN is not set")

    url = env.get("TAPD_MCP_URL") or DEFAULT_TAPD_MCP_URL
    return _jsonrpc_initialize(
        name="TAPD MCP",
        url=url,
        headers={"X-Tapd-Access-Token": token},
        timeout=timeout,
    )


def check_iwiki(env: Mapping[str, str], timeout: float) -> CheckResult:
    token = env.get("TAI_PAT_TOKEN") or env.get("IWIKI_MCP_TOKEN", "")
    if not token:
        return CheckResult("iWiki MCP", False, "TAI_PAT_TOKEN or IWIKI_MCP_TOKEN is not set")

    url = env.get("IWIKI_MCP_URL") or DEFAULT_IWIKI_MCP_URL
    auth = token if token.startswith("Bearer ") else f"Bearer {token}"
    return _jsonrpc_initialize(
        name="iWiki MCP",
        url=url,
        headers={"Authorization": auth},
        timeout=timeout,
    )


def check_gongfeng_rest(env: Mapping[str, str], timeout: float) -> CheckResult:
    token = env.get("GONGFENG_ACCESS_TOKEN", "")
    if not token:
        return CheckResult("Gongfeng REST", False, "GONGFENG_ACCESS_TOKEN is not set")

    request = urllib.request.Request(
        DEFAULT_GONGFENG_API_URL,
        headers={"PRIVATE-TOKEN": token},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            data = json.loads(body)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return CheckResult("Gongfeng REST", False, _safe_error(exc))

    if data.get("id"):
        return CheckResult("Gongfeng REST", True, "authenticated /user request")
    return CheckResult("Gongfeng REST", False, "response did not contain a user id")


def check_tgit_mcp(env: Mapping[str, str], timeout: float) -> CheckResult:
    token = env.get("GONGFENG_ACCESS_TOKEN", "")
    if not token:
        return CheckResult("TGit MCP", False, "GONGFENG_ACCESS_TOKEN is not set")

    package = env.get("TGIT_MCP_PACKAGE") or DEFAULT_TGIT_MCP_PACKAGE
    return _run_command_probe(
        name="TGit MCP",
        command=["npx", "-y", package, "--help"],
        env={**os.environ, **env},
        timeout=timeout,
        expected=("Gongfeng MCP Server", "Usage"),
    )


def check_playwright_mcp(env: Mapping[str, str], timeout: float) -> CheckResult:
    package = env.get("PLAYWRIGHT_MCP_PACKAGE") or DEFAULT_PLAYWRIGHT_MCP_PACKAGE
    return _run_command_probe(
        name="Playwright MCP",
        command=["npx", "-y", package, "--help"],
        env={**os.environ, **env},
        timeout=max(timeout, 20.0),
        expected=("Usage: Playwright MCP",),
    )


def check_playwright_browser(env: Mapping[str, str], timeout: float) -> CheckResult:
    script = r'''
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright package is not installed; run uv sync --extra codex --extra e2e --group dev")
    raise SystemExit(1)

try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        browser.close()
except Exception as exc:
    print(f"chromium launch failed; run uv run python -m playwright install chromium: {exc}")
    raise SystemExit(1)

print("playwright-browser-ok")
'''
    return _run_command_probe(
        name="Playwright Browser",
        command=[sys.executable, "-c", script],
        env={**os.environ, **env},
        timeout=max(timeout, 20.0),
        expected=("playwright-browser-ok",),
    )


def render_summary(results: list[CheckResult]) -> str:
    lines = ["# AI Test Officer Doctor", ""]
    for result in results:
        lines.append(f"- [{result.status}] {result.name}: {result.detail}")
    lines.append("")
    if all(result.passed for result in results):
        lines.append("All integration checks passed.")
    else:
        lines.append("One or more integration checks failed.")
    return "\n".join(lines)


def exit_code(results: list[CheckResult]) -> int:
    return 0 if all(result.passed for result in results) else 1


def _jsonrpc_initialize(
    name: str,
    url: str,
    headers: Mapping[str, str],
    timeout: float,
) -> CheckResult:
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "ai-test-officer-doctor", "version": "0.1.0"},
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **dict(headers),
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError) as exc:
        return CheckResult(name, False, _safe_error(exc))

    if '"serverInfo"' in body:
        return CheckResult(name, True, "initialize returned serverInfo")
    return CheckResult(name, False, "initialize response did not contain serverInfo")


def _run_command_probe(
    name: str,
    command: list[str],
    env: Mapping[str, str],
    timeout: float,
    expected: tuple[str, ...],
) -> CheckResult:
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=dict(env),
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckResult(name, False, _safe_error(exc))

    output = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode == 0 and any(marker in output for marker in expected):
        return CheckResult(name, True, "command probe succeeded")

    detail = _last_nonempty_line(output) or f"command exited {proc.returncode}"
    return CheckResult(name, False, _redact(detail, env))


def _last_nonempty_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _safe_error(exc: BaseException) -> str:
    return _redact(str(exc), os.environ)


def _redact(text: str, env: Mapping[str, str]) -> str:
    redacted = text
    for key in SECRET_KEYS:
        value = env.get(key)
        if value:
            redacted = redacted.replace(value, "<redacted>")
    return redacted
