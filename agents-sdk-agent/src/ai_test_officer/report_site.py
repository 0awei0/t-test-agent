from __future__ import annotations

import posixpath
import json
import shutil
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .models import RunRecord
from .redaction import redact_secrets

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


@dataclass(frozen=True)
class PublishedReport:
    site_root: Path
    run_dir: Path
    index_path: Path
    detail_url: str | None


@dataclass(frozen=True)
class FueStaticProject:
    project_root: Path
    public_dir: Path
    index_path: Path
    config_path: Path
    deploy_doc_path: Path


def publish_record(
    record: RunRecord,
    *,
    site_root: Path | None = None,
    base_url: str | None = None,
) -> PublishedReport:
    root = (site_root or record.run_dir / "site").expanduser().resolve()
    run_dir_name = _run_dir_name(record)
    run_dir = root / run_dir_name
    run_dir.mkdir(parents=True, exist_ok=True)

    index_path = run_dir / "index.html"
    shutil.copy2(record.html_path, index_path)
    _copy_if_exists(record.report_path, run_dir / "report.md")
    _copy_if_exists(record.json_path, run_dir / "run.json")
    _copy_evidence(record, run_dir)

    detail_url = _detail_url(base_url, run_dir_name) if base_url else None
    record.detail_url = detail_url
    record.published_report_path = index_path
    _update_run_json(record)
    return PublishedReport(root, run_dir, index_path, detail_url)


def publish_report_path(
    report_path: Path,
    *,
    site_root: Path | None = None,
    base_url: str | None = None,
) -> PublishedReport:
    report = report_path.expanduser().resolve()
    run_dir_source = report.parent
    html_path = run_dir_source / "report.html"
    if not html_path.exists():
        raise FileNotFoundError(f"missing report html next to markdown: {html_path}")
    root = (site_root or run_dir_source / "site").expanduser().resolve()
    run_dir_name = _run_dir_name_from_path(report)
    run_dir = root / run_dir_name
    run_dir.mkdir(parents=True, exist_ok=True)
    index_path = run_dir / "index.html"
    shutil.copy2(html_path, index_path)
    _copy_if_exists(report, run_dir / "report.md")
    _copy_if_exists(run_dir_source / "run.json", run_dir / "run.json")
    _copy_relative_artifacts(run_dir_source, run_dir)
    return PublishedReport(root, run_dir, index_path, _detail_url(base_url, run_dir_name) if base_url else None)


def export_fue_static_project(
    report_path: Path,
    *,
    output: Path | None = None,
    project_slug: str = "ai-test-officer-report",
    project_name: str = "AI Test Officer Report",
) -> FueStaticProject:
    report = report_path.expanduser().resolve()
    run_dir_source = report.parent
    html_path = run_dir_source / "report.html"
    if not html_path.exists():
        raise FileNotFoundError(f"missing report html next to markdown: {html_path}")

    project_root = (output or Path("runs") / "fue-site" / _safe_run_dir_name(run_dir_source.name)).expanduser().resolve()
    public_dir = project_root / "public"
    public_dir.mkdir(parents=True, exist_ok=True)

    index_path = public_dir / "index.html"
    run_metadata = _read_run_json(run_dir_source / "run.json")
    _copy_sanitized_text_file(html_path, index_path, run_metadata)
    _copy_sanitized_text_file(report, public_dir / "report.md", run_metadata)
    _write_public_run_json(run_dir_source / "run.json", public_dir / "public-run.json")
    _copy_relative_artifacts(run_dir_source, public_dir)
    _bundle_live_dashboard(run_dir_source, public_dir / "dashboard", run_metadata)

    config_path = project_root / "fue.json"
    config_path.write_text(
        json.dumps(_fue_static_config(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    package_path = project_root / "package.json"
    package_path.write_text(
        json.dumps(_fue_package_json(project_slug), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    deploy_doc_path = project_root / "FUE_DEPLOY.md"
    deploy_doc_path.write_text(
        _fue_deploy_doc(project_slug=project_slug, project_name=project_name),
        encoding="utf-8",
    )
    return FueStaticProject(project_root, public_dir, index_path, config_path, deploy_doc_path)


def serve_report_site(root: Path, *, host: str = "0.0.0.0", port: int = 8788) -> None:
    site_root = root.expanduser().resolve()
    site_root.mkdir(parents=True, exist_ok=True)
    handler = partial(SimpleHTTPRequestHandler, directory=str(site_root))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Serving AI Test Officer reports from {site_root} at http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped AI Test Officer report server.")
    finally:
        server.server_close()


def _copy_evidence(record: RunRecord, published_run_dir: Path) -> None:
    for source in record.evidence_files:
        if not source.exists() or not source.is_file():
            continue
        try:
            rel = source.relative_to(record.run_dir)
        except ValueError:
            rel = Path("assets") / source.name
        target = published_run_dir / rel
        _copy_if_exists(source, target)


def _copy_relative_artifacts(source_run_dir: Path, published_run_dir: Path) -> None:
    for relative_root in (Path("repo") / "reports" / "evidence", Path("evidence")):
        source_root = source_run_dir / relative_root
        if not source_root.exists():
            continue
        for source in source_root.rglob("*"):
            if not source.is_file():
                continue
            target = published_run_dir / source.relative_to(source_run_dir)
            _copy_if_exists(source, target)


def _bundle_live_dashboard(
    source_run_dir: Path,
    dashboard_dir: Path,
    run_metadata: dict[str, Any],
) -> None:
    """Bundle the built React live dashboard as a self-contained static replay.

    The dashboard reads ``events.jsonl`` (and evidence/report siblings) from its
    own directory via ``?mode=static``, so it works inside a FUE static package
    with no backend. A minimal replay landing page is emitted when the React
    frontend has not been built, keeping clean-checkout exports complete.
    """
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    if FRONTEND_DIST.exists():
        shutil.copytree(FRONTEND_DIST, dashboard_dir, dirs_exist_ok=True)
    else:
        (dashboard_dir / "index.html").write_text(_fallback_dashboard_html(), encoding="utf-8")
    _copy_sanitized_events(source_run_dir / "events.jsonl", dashboard_dir / "events.jsonl", run_metadata)
    _copy_sanitized_text_file(source_run_dir / "report.html", dashboard_dir / "report.html", run_metadata)
    for sub in (Path("repo") / "reports" / "evidence", Path("evidence")):
        src = source_run_dir / sub
        if src.is_dir():
            shutil.copytree(src, dashboard_dir / sub, dirs_exist_ok=True)


def _fallback_dashboard_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Test Officer Replay</title></head>
<body><main><h1>AI 测试官执行回放</h1>
<p>完整交互仪表盘尚未构建；本目录仍包含脱敏事件、报告和合成证据。</p>
<p><a href="report.html">查看测试报告</a> · <a href="events.jsonl">查看脱敏事件</a></p>
</main></body></html>
"""


def _copy_sanitized_events(source: Path, target: Path, run_metadata: dict[str, Any]) -> None:
    if not source.exists() or not source.is_file():
        return
    lines: list[str] = []
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        scrubbed = _scrub_event(event, run_metadata)
        lines.append(json.dumps(scrubbed, ensure_ascii=False))
    if lines:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _scrub_event(value: Any, run_metadata: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {str(key): _scrub_event(item, run_metadata) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub_event(item, run_metadata) for item in value]
    if isinstance(value, str):
        return _scrub_public_text(value, run_metadata)[:2_000]
    return value


def _copy_if_exists(source: Path, target: Path) -> None:
    if not source.exists() or not source.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_sanitized_text_file(source: Path, target: Path, run_metadata: dict[str, Any]) -> None:
    if not source.exists() or not source.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    text = source.read_text(encoding="utf-8", errors="replace")
    target.write_text(_scrub_public_text(text, run_metadata), encoding="utf-8")


def _write_public_run_json(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    data = _read_run_json(source)
    public_data = _public_run_json(data)
    target.write_text(json.dumps(public_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_run_json(source: Path) -> dict[str, Any]:
    if not source.exists() or not source.is_file():
        return {}
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _public_run_json(data: dict[str, Any]) -> dict[str, Any]:
    run_dir = str(data.get("run_dir") or "")
    commands = []
    for item in data.get("commands", []):
        if not isinstance(item, dict):
            continue
        output_text = "\n".join(
            str(item.get(key) or "")
            for key in ("stderr", "stdout")
            if str(item.get(key) or "").strip()
        )
        commands.append(
            _redact_structure(
                {
                    "command": item.get("command"),
                    "returncode": item.get("returncode"),
                    "failure_category": item.get("failure_category"),
                    "log_path": _public_path(item.get("log_path"), run_dir),
                    "output_summary": _public_output_summary(output_text),
                }
            )
        )

    memory = data.get("memory_summary") if isinstance(data.get("memory_summary"), dict) else {}
    public_data = {
        "run_id": data.get("run_id"),
        "task": data.get("task"),
        "git_range": data.get("git_range"),
        "mr_url": data.get("mr_url"),
        "mr_project": data.get("mr_project"),
        "mr_iid": data.get("mr_iid"),
        "mr_title": data.get("mr_title"),
        "checkout_strategy": data.get("checkout_strategy"),
        "checkout_status": data.get("checkout_status"),
        "checkout_error": data.get("checkout_error"),
        "changed_files": data.get("changed_files", []),
        "context_strategy": data.get("context_strategy"),
        "skill_used": data.get("skill_used"),
        "mcp_servers": data.get("mcp_servers", []),
        "planner_mode": data.get("planner_mode"),
        "planner_trace": data.get("planner_trace", []),
        "tools_used": data.get("tools_used", []),
        "agent_turns": data.get("agent_turns", []),
        "required_tool_check": data.get("required_tool_check", {}),
        "memory_summary": {
            "mode": memory.get("mode"),
            "source_chars": memory.get("source_chars"),
            "summary_chars": memory.get("summary_chars"),
            "compression_ratio": memory.get("compression_ratio"),
            "summary_path": _public_path(memory.get("summary_path"), run_dir),
            "artifact_paths": [_public_path(item, run_dir) for item in memory.get("artifact_paths", [])],
            "used_model": memory.get("used_model"),
            "status": memory.get("status"),
        },
        "failure_category": data.get("failure_category"),
        "blocked_reason": data.get("blocked_reason"),
        "agent_final_output": data.get("agent_final_output"),
        "allow_temp_test_code": data.get("allow_temp_test_code"),
        "generated_files": [
            {
                "path": _public_path(item.get("path"), run_dir),
                "reason": item.get("reason"),
            }
            for item in data.get("generated_files", [])
            if isinstance(item, dict)
        ],
        "evidence_files": [_public_path(item, run_dir) for item in data.get("evidence_files", [])],
        "commands": commands,
        "verdict": data.get("verdict"),
        "risk": data.get("risk"),
        "summary": data.get("summary"),
        "detail_url": data.get("detail_url"),
    }
    return _redact_structure(public_data)


def _public_path(value: Any, run_dir: str) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        return text
    path = Path(text)
    if run_dir:
        try:
            return str(path.relative_to(run_dir))
        except ValueError:
            pass
    if path.is_absolute():
        return "<local-path>"
    return text


def _public_output_summary(text: str, limit: int = 500) -> str:
    text = redact_secrets(text.strip())
    if not text:
        return ""
    interesting = []
    keywords = ("error", "failed", "failure", "assert", "cannot find", "not found", "traceback", "panic")
    for line in text.splitlines():
        lower = line.lower()
        if any(keyword in lower for keyword in keywords):
            interesting.append(line.strip())
        if len(interesting) >= 6:
            break
    summary = "\n".join(interesting) if interesting else text
    if len(summary) <= limit:
        return summary
    head = max(0, limit - 120)
    return f"{summary[:head].rstrip()}\n...[public output summary truncated]..."


def _scrub_public_text(text: str, run_metadata: dict[str, Any]) -> str:
    replacements = {
        str(run_metadata.get("source_repo") or ""): "<source-repo>",
        str(run_metadata.get("workspace_repo") or ""): "<isolated-workspace>",
        str(run_metadata.get("run_dir") or ""): "<run-dir>",
    }
    scrubbed = text
    for source, replacement in replacements.items():
        if source:
            scrubbed = scrubbed.replace(source, replacement)
    return redact_secrets(scrubbed)


def _redact_structure(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_structure(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_structure(item) for item in value]
    if isinstance(value, str):
        return redact_secrets(value)
    return value


def _run_dir_name(record: RunRecord) -> str:
    return _safe_run_dir_name(record.run_id)


def _run_dir_name_from_path(report: Path) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return _safe_run_dir_name(f"{timestamp}-{report.parent.name}")


def _safe_run_dir_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value) or "report"


def _detail_url(base_url: str | None, run_dir_name: str) -> str | None:
    if not base_url:
        return None
    base = base_url.rstrip("/")
    quoted_run_dir = urllib.parse.quote(run_dir_name, safe="-_.")
    return posixpath.join(base, quoted_run_dir, "index.html")


def _update_run_json(record: RunRecord) -> None:
    if not record.json_path.exists():
        return
    data = json.loads(record.json_path.read_text(encoding="utf-8"))
    data["detail_url"] = record.detail_url
    data["published_report_path"] = str(record.published_report_path) if record.published_report_path else None
    record.json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _fue_static_config() -> dict:
    return {
        "type": "web",
        "framework": {
            "name": "Other",
            "installCommand": "",
            "buildCommand": "",
            "outputDirectory": "public",
        },
        "rootDirectory": "./",
        "installCmd": "",
        "buildCmd": "",
        "outputDirectory": "public",
        "deployConfig": {
            "enableStatic": True,
            "enableContainer": False,
            "deployDirectory": "./",
            "staticDirectory": "public",
        },
    }


def _fue_package_json(project_slug: str) -> dict:
    return {
        "name": _safe_package_name(project_slug),
        "private": True,
        "version": "0.0.0",
        "scripts": {
            "build": "node -e \"require('fs').mkdirSync('public', { recursive: true })\"",
        },
    }


def _safe_package_name(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized or "ai-test-officer-report"


def _fue_deploy_doc(*, project_slug: str, project_name: str) -> str:
    return f"""# FUE 部署文档（AI Test Officer 报告 + 实时仪表盘回放）

本目录是通过 `ai-test-officer report export-fue` 生成的**静态 Web 应用**，用于把一次
AI 测试官的运行结果（含实时执行仪表盘回放页）部署到 FUE 静态托管，方便评审/分享。

> 安全提醒：不要把业务报告原文、截图、运行日志提交进 Git 仓库。`public/` 里只放脱敏后的
> `public-run.json` 和 `report.md`；完整的本地 `run.json`、日志、本地绝对路径**不会**被导出。

---

## 0. 前置条件

部署前请确认本机满足：

1. **Node.js ≥ 18** 和 npm（用于安装/调用 FUE CLI）。
   ```bash
   node -v && npm -v
   ```
2. **能访问 FUE 内网**，且已获得 FUE 账号（企业微信/OA 登录）。
3. 安装 FUE CLI 并完成登录：
   ```bash
   npm i -g @tencent/fue-cli
   fue login          # 按提示用企业微信/OA 扫码或填 token
   fue whoami         # 确认已登录
   ```
4. **实时仪表盘需要前端先构建**（否则 `public/dashboard/` 会被跳过，只有主报告页）：
   ```bash
   cd <仓库根>/frontend
   npm install
   npm run build      # 产物输出到 frontend/dist/
   ```

---

## 1. 包结构说明

```text
{project_slug}/
├── fue.json            # FUE 工程配置（已按下方控制台参数生成）
├── package.json        # FUE 工程元信息
├── FUE_DEPLOY.md       # 本文件
└── public/             # ← FUE 部署目录（Static Directory）
    ├── index.html      # 主报告页（部署后访问 /）
    ├── report.md       # 完整测试报告（Markdown）
    ├── public-run.json # 脱敏后的运行数据（供调试）
    └── dashboard/      # ★ 实时执行仪表盘回放页（无后端）
        ├── index.html
        ├── events.jsonl   # 本次运行的事件流（阶段/工具调用/命令/证据/结论）
        ├── assets/        # 构建后的 JS/CSS（相对路径引用）
        ├── evidence/      # 截图/日志证据
        ├── logs/          # 命令执行日志
        └── report.html    # 完整 HTML 报告
```

若 `public/dashboard/` 不存在，说明导出时 `frontend/dist` 尚未构建，请回到第 0 步
`npm run build` 后**重新导出**（见第 5 节）。

---

## 2. 方式一：FUE 控制台（UI，推荐）

适合不熟悉 CLI 的情况，全程网页操作。

1. 打开 FUE 控制台，新建**静态 Web 应用**（Static Web / 静态托管）。
2. 关联/上传本目录 `{project_slug}/`（整目录上传，或关联代码仓库该路径）。
3. 在构建/部署配置中按如下填写：

   | 配置项 | 值 |
   | --- | --- |
   | 工程类型 | 静态Web应用 |
   | 框架预设 | Other |
   | 部署方式 | 静态托管 (COS + CDN) |
   | Root Directory | `./` |
   | **Static Directory** | **`public`** |
   | 访问路径 | `/` |

   （`fue.json` 已经包含了这些字段，控制台导入配置时可自动识别。）
4. 点击**部署**，等待构建完成。
5. FUE 会分配一个测试域名，形如 `https://<项目标识>.fue.woa.com/`。

部署完成后：

- 主报告页：`https://<项目标识>.fue.woa.com/`
- **实时仪表盘回放页**：`https://<项目标识>.fue.woa.com/dashboard/?mode=static`

仪表盘会读取同目录下的 `events.jsonl`，完整还原
「理解 → 规划 → 执行 → 校验 → 报告」的过程时间线、失败定位与证据网格，无需任何后端。

---

## 3. 方式二：FUE CLI

```bash
# 进入导出的包目录
cd {project_slug}

# 首次部署：创建 FUE 项目
fue project create

# 已有 FUE 项目则改为关联，无需重新创建
# fue link

# 部署（--cwd 指定包根目录，--default 使用默认环境）
fue deploy --cwd . --default
```

部署成功后终端会打印访问地址，把 `https://*.fue.woa.com/...` 填进 showcase 通知的
`--detail-url` 即可（见仓库 README 的「Competition Showcase」）。

---

## 4. 部署前自检清单

部署前请确认：

- [ ] `fue whoami` 已登录，且本机可访问 FUE。
- [ ] `public/index.html` 存在。
- [ ] `public/dashboard/events.jsonl` 存在且非空（决定仪表盘能否回放）。
- [ ] `public/dashboard/assets/` 下有两个构建产物（JS/CSS）。
- [ ] 本地已用浏览器打开 `public/dashboard/index.html` 验证过渲染（可用
      `python -m http.server` 在该目录起一个临时静态服务预览）。

快速预览命令（部署前本地自查）：

```bash
cd public/dashboard
python -m http.server 8080
# 浏览器打开 http://127.0.0.1:8080/?mode=static
```

---

## 5. 重新导出（改了前端 / 换了 run）

如果更新了 `frontend/` 代码，或要部署另一次运行，需要先重新构建并重新导出：

```bash
# 1) 重新构建前端
cd <仓库根>/frontend && npm run build && cd ..

# 2) 重新导出 FUE 包（覆盖原目录）
uv run ai-test-officer report export-fue \
  --report runs/<run-id>/report.md \
  --output runs/fue-site/<run-id> \
  --project-slug {project_slug}

# 3) 回到第 2 / 第 3 节重新部署
```

---

## 6. 常见问题排查

| 现象 | 原因 / 解决 |
| --- | --- |
| 仪表盘页 404 | 部署路径不对：确认 Static Directory 是 `public`，且访问 `/dashboard/` 而非根。 |
| 仪表盘空白 / 一直“连接中…” | `public/dashboard/events.jsonl` 缺失或空 → 前端没构建或没重新导出（见第 5 节）。 |
| 资源 404（JS/CSS 加载不出） | 前端构建须用相对路径（`vite.config.ts` 已设 `base: "./"`）。若改过配置需重新 `npm run build`。 |
| 控制台导入配置报错 | 直接按第 2 节表格手动填，不依赖 `fue.json` 自动识别。 |
| 报告里出现本地绝对路径 | 不应发生；`public-run.json` 已脱敏。若 `index.html` 含 `file://` 说明导出异常，重新导出。 |

---

测试环境使用 FUE 分配的默认 `*.fue.woa.com` 域名即可。只有绑定正式自有域名时，
才需要业务侧准备 DNS/CNAME 和 HTTPS 证书。
"""
