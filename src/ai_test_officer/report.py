from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import TestTask


def write_report(task: TestTask, body: str, dry_run: bool = False, scenario: str | None = None) -> Path:
    output_path = task.resolved_output()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    mode = "dry-run" if dry_run else "codex-sdk"
    report = f"""<!-- generated-by: ai_test_officer -->
<!-- mode: {mode} -->
<!-- generated-at: {generated_at} -->

{body.rstrip()}
"""
    output_path.write_text(report, encoding="utf-8")
    write_run_json(
        task=task,
        body=body,
        report_path=output_path,
        mode=mode,
        generated_at=generated_at,
        scenario=scenario,
    )
    return output_path


def run_json_path_for(report_path: Path) -> Path:
    return report_path.with_suffix(".json")


def write_run_json(
    *,
    task: TestTask,
    body: str,
    report_path: Path,
    mode: str,
    generated_at: str,
    scenario: str | None = None,
) -> Path:
    metadata = build_run_metadata(
        task=task,
        body=body,
        report_path=report_path,
        mode=mode,
        generated_at=generated_at,
        scenario=scenario,
    )
    path = run_json_path_for(report_path)
    path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build_run_metadata(
    *,
    task: TestTask,
    body: str,
    report_path: Path,
    mode: str,
    generated_at: str,
    scenario: str | None = None,
) -> dict[str, Any]:
    sections = _parse_sections(body)
    safe_sections = {
        key: value
        for key, value in sections.items()
        if key
        in {
            "Summary",
            "Scope",
            "Changed Files / Risk Map",
            "Test Strategy",
            "Execution",
            "Findings",
            "Recommended Next Steps",
        }
    }
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "mode": mode,
        "scenario": scenario,
        "task": task.task,
        "repo": str(task.resolved_repo()),
        "report_path": str(report_path),
        "verdict": _extract_bullet_value(body, "Verdict") or "needs-follow-up",
        "risk": _extract_bullet_value(body, "Risk") or "medium",
        "changed_files": _changed_files(task, sections),
        "timeline": _timeline(mode, sections),
        "commands": _commands(sections),
        "artifacts": _artifacts(report_path, body),
        "sections": safe_sections,
    }


def dry_run_report(prompt: str) -> str:
    return f"""# AI Test Officer Report

## Summary
- Verdict: needs-follow-up
- Risk: medium
- Dry run only. Codex SDK was not called.

## Scope
- Generated the prompt that would be sent to Codex.

## Test Strategy
- Review the generated prompt for scope and safety.
- Install the `codex` extra and run without `--dry-run` to execute the workflow.

## Execution
- No project commands were run.

## Findings
- No runtime findings are available in dry-run mode.

## Recommended Next Steps
- Run the command again without `--dry-run` when ready.

## Prompt Preview

```text
{prompt.rstrip()}
```
"""


def _parse_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in markdown.splitlines():
        if raw_line.startswith("## "):
            current = raw_line[3:].strip()
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(raw_line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def _extract_bullet_value(markdown: str, label: str) -> str | None:
    pattern = re.compile(rf"^\s*-\s*{re.escape(label)}:\s*(.+?)\s*$", re.IGNORECASE)
    for line in markdown.splitlines():
        match = pattern.match(line)
        if match:
            return match.group(1).strip()
    return None


def _changed_files(task: TestTask, sections: dict[str, str]) -> list[str]:
    if task.changed_files:
        return [line.strip() for line in task.changed_files.splitlines() if line.strip()]

    section = sections.get("Changed Files / Risk Map", "")
    return _bullet_lines(section)


def _timeline(mode: str, sections: dict[str, str]) -> list[dict[str, str]]:
    execution = sections.get("Execution", "")
    execution_status = "skipped" if "No project commands were run" in execution else "done"
    if mode != "dry-run" and execution_status == "skipped":
        execution_status = "unknown"

    return [
        {"name": "Understand", "status": "done", "detail": "Read request and available context."},
        {"name": "Plan", "status": "done", "detail": "Produced or requested a test strategy."},
        {"name": "Execute", "status": execution_status, "detail": _first_sentence(execution)},
        {"name": "Report", "status": "done", "detail": "Wrote Markdown report and JSON metadata."},
    ]


def _commands(sections: dict[str, str]) -> list[str]:
    execution = sections.get("Execution", "")
    commands = []
    for line in _bullet_lines(execution):
        if "`" in line or "python" in line or "uv " in line or "npm " in line or "playwright" in line.lower():
            commands.append(line)
    return commands[:12]


def _artifacts(report_path: Path, markdown: str) -> list[dict[str, str]]:
    artifacts: dict[str, dict[str, str]] = {}
    evidence_dir = report_path.parent / "evidence"
    if evidence_dir.exists():
        for path in evidence_dir.glob("*"):
            if path.is_file():
                artifacts[str(path)] = _artifact_record(path)

    pattern = re.compile(r"(?P<path>(?:[\w./:-]+)?reports/evidence/[\w./-]+\.(?:png|jpg|jpeg|webp))")
    for match in pattern.finditer(markdown):
        raw = match.group("path").strip("`'\"),.")
        artifacts.setdefault(raw, _artifact_record(Path(raw)))
    return list(artifacts.values())


def _artifact_record(path: Path) -> dict[str, str]:
    kind = "screenshot" if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} else "file"
    return {"kind": kind, "path": str(path), "label": path.name}


def _bullet_lines(section: str) -> list[str]:
    lines = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if line.startswith("- "):
            lines.append(line[2:].strip())
    return lines


def _first_sentence(text: str) -> str:
    compact = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if not compact:
        return "No execution detail was captured."
    return compact[:180]
