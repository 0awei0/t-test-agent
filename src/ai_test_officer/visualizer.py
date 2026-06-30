from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any


def visualize_report(report_path: Path, run_json_path: Path, output_path: Path | None = None) -> Path:
    report = report_path.expanduser().resolve()
    run_json = run_json_path.expanduser().resolve()
    output = (output_path or report.with_suffix(".html")).expanduser()
    if not output.is_absolute():
        output = report.parent / output
    output.parent.mkdir(parents=True, exist_ok=True)

    data = json.loads(run_json.read_text(encoding="utf-8"))
    markdown = report.read_text(encoding="utf-8", errors="replace")
    output.write_text(_render_html(data, markdown, output), encoding="utf-8")
    return output


def _render_html(data: dict[str, Any], markdown: str, output_path: Path) -> str:
    title = "AI Test Officer Report"
    scenario = data.get("scenario") or "custom"
    verdict = data.get("verdict") or "needs-follow-up"
    risk = data.get("risk") or "medium"
    task = data.get("task") or ""
    sections = data.get("sections") or {}

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{html.escape(title)}</title>
    <style>
      :root {{
        color-scheme: light;
        --ink: #172033;
        --muted: #5d667a;
        --line: #d8dee9;
        --panel: #ffffff;
        --bg: #f5f7fb;
        --accent: #0b6bcb;
        --danger: #b42318;
      }}
      body {{
        margin: 0;
        background: var(--bg);
        color: var(--ink);
        font-family: Arial, "Microsoft YaHei", sans-serif;
        line-height: 1.5;
      }}
      header {{
        padding: 28px 36px 20px;
        background: #ffffff;
        border-bottom: 1px solid var(--line);
      }}
      h1 {{ margin: 0 0 8px; font-size: 28px; }}
      h2 {{ margin: 0 0 12px; font-size: 18px; }}
      main {{
        display: grid;
        grid-template-columns: minmax(0, 1fr) 320px;
        gap: 18px;
        padding: 20px 36px 36px;
      }}
      section, aside {{
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 18px;
      }}
      .meta {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        color: var(--muted);
      }}
      .pill {{
        display: inline-flex;
        align-items: center;
        min-height: 28px;
        padding: 0 10px;
        border: 1px solid var(--line);
        border-radius: 999px;
        background: #f8fafc;
        font-size: 13px;
      }}
      .verdict-fail, .risk-high {{ color: var(--danger); font-weight: 700; }}
      .grid {{ display: grid; gap: 18px; }}
      ul {{ margin: 0; padding-left: 20px; }}
      li + li {{ margin-top: 6px; }}
      pre {{
        overflow: auto;
        white-space: pre-wrap;
        background: #101828;
        color: #f8fafc;
        padding: 14px;
        border-radius: 6px;
      }}
      .timeline {{
        position: relative;
        list-style: none;
        padding-left: 0;
      }}
      .timeline li {{
        border-left: 3px solid var(--accent);
        padding: 0 0 14px 12px;
      }}
      .timeline strong {{ display: block; }}
      .muted {{ color: var(--muted); }}
      .artifact img {{
        max-width: 100%;
        border: 1px solid var(--line);
        border-radius: 6px;
      }}
      @media (max-width: 900px) {{
        main {{ grid-template-columns: 1fr; padding: 16px; }}
        header {{ padding: 22px 16px 16px; }}
      }}
    </style>
  </head>
  <body>
    <header>
      <h1>{html.escape(title)}</h1>
      <div class="meta">
        <span class="pill">Scenario: {html.escape(str(scenario))}</span>
        <span class="pill verdict-{html.escape(str(verdict))}">Verdict: {html.escape(str(verdict))}</span>
        <span class="pill risk-{html.escape(str(risk))}">Risk: {html.escape(str(risk))}</span>
        <span class="pill">Mode: {html.escape(str(data.get("mode", "")))}</span>
      </div>
      <p>{html.escape(str(task))}</p>
    </header>
    <main>
      <div class="grid">
        {_section("Timeline", _timeline(data.get("timeline") or []))}
        {_section("Changed Files", _list(data.get("changed_files") or ["No changed files captured."]))}
        {_section("Findings", _markdown_fragment(sections.get("Findings", "")))}
        {_section("Execution", _execution(data))}
        {_section("Report", f"<pre>{html.escape(_strip_comments(markdown))}</pre>")}
      </div>
      <aside>
        <h2>Evidence</h2>
        {_artifacts(data.get("artifacts") or [], output_path)}
      </aside>
    </main>
  </body>
</html>
"""


def _section(title: str, body: str) -> str:
    return f"<section><h2>{html.escape(title)}</h2>{body}</section>"


def _list(items: list[Any]) -> str:
    return "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in items) + "</ul>"


def _timeline(items: list[dict[str, str]]) -> str:
    rows = []
    for item in items:
        rows.append(
            "<li>"
            f"<strong>{html.escape(item.get('name', 'Step'))}"
            f" <span class=\"muted\">{html.escape(item.get('status', 'unknown'))}</span></strong>"
            f"<span>{html.escape(item.get('detail', ''))}</span>"
            "</li>"
        )
    return "<ol class=\"timeline\">" + "".join(rows) + "</ol>"


def _execution(data: dict[str, Any]) -> str:
    commands = data.get("commands") or []
    if commands:
        return "<h3>Commands</h3>" + _list(commands)
    return "<p class=\"muted\">No command summary was captured.</p>"


def _artifacts(items: list[dict[str, str]], output_path: Path) -> str:
    if not items:
        return "<p class=\"muted\">No screenshot or file artifact was captured.</p>"

    rendered = []
    for item in items:
        path = item.get("path", "")
        label = item.get("label") or Path(path).name
        src = _artifact_src(path, output_path)
        if item.get("kind") == "screenshot":
            rendered.append(
                "<div class=\"artifact\">"
                f"<p>{html.escape(label)}</p>"
                f"<img src=\"{html.escape(src)}\" alt=\"{html.escape(label)}\" />"
                "</div>"
            )
        else:
            rendered.append(f"<p>{html.escape(label)}: <code>{html.escape(path)}</code></p>")
    return "".join(rendered)


def _artifact_src(path: str, output_path: Path) -> str:
    artifact = Path(path)
    if artifact.is_absolute():
        return artifact.as_uri()
    if artifact.parts[:2] == ("reports", "evidence"):
        candidate = output_path.parent.parent / artifact
        if candidate.exists():
            return os.path.relpath(candidate, output_path.parent)
    return artifact.as_posix()


def _markdown_fragment(text: str) -> str:
    if not text:
        return "<p class=\"muted\">No findings captured.</p>"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    bullets = [line[2:] for line in lines if line.startswith("- ")]
    if bullets:
        return _list(bullets)
    return f"<pre>{html.escape(text)}</pre>"


def _strip_comments(markdown: str) -> str:
    return "\n".join(line for line in markdown.splitlines() if not line.strip().startswith("<!--")).strip()
