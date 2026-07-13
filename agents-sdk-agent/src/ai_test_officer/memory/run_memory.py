from __future__ import annotations

from pathlib import Path

from .types import PromptBudget
from ..config import DEFAULT_PROMPT_BUDGET_CHARS
from ..models import MemorySummary, RunRecord
from ..prompts import load_prompt
from ..redaction import redact_secrets


DEFAULT_PROMPT_BUDGET = PromptBudget(max_chars=DEFAULT_PROMPT_BUDGET_CHARS)


def build_agent_summary_prompt(record: RunRecord, budget: PromptBudget = DEFAULT_PROMPT_BUDGET) -> str:
    changed = "\n".join(f"{item.status}\t{item.path}" for item in record.changed_files) or "None"
    commands = "\n".join(_command_summary(item.command, item.returncode, item.stdout, item.stderr) for item in record.commands) or "None"
    generated = "\n".join(str(item.path.relative_to(record.run_dir)) for item in record.generated_files) or "None"
    context = record.context_summary or "No context summary was generated."
    prompt = f"""Summarize this AI Test Officer run in Chinese.

Task: {record.task}
MR: {record.mr_project or "local"}{f"!{record.mr_iid}" if record.mr_iid is not None else ""}
Verdict: {record.verdict}
Risk: {record.risk}
Summary: {record.summary}
Context strategy: {record.context_strategy or "unknown"}

Context summary:
{context}

Changed files:
{changed}

Generated files:
{generated}

Commands:
{commands}
"""
    return compact_text(prompt, budget.max_chars)


def build_run_memory(record: RunRecord, *, mode: str = "structured") -> MemorySummary:
    if mode not in {"structured", "model"}:
        raise ValueError(f"unsupported memory mode: {mode}")
    memory_dir = record.run_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    raw_context = _raw_context(record)
    if mode == "model":
        summary, used_model = _model_context_summary(raw_context)
        if not summary:
            summary, used_model = _structured_context_summary(record), False
    else:
        summary, used_model = _structured_context_summary(record), False
    summary_path = memory_dir / "context_summary.md"
    summary_path.write_text(summary, encoding="utf-8")
    source_chars = len(raw_context)
    summary_chars = len(summary)
    ratio = round(summary_chars / source_chars, 4) if source_chars else 1.0
    return MemorySummary(
        mode=mode,
        source_chars=source_chars,
        summary_chars=summary_chars,
        compression_ratio=ratio,
        summary_path=summary_path,
        artifact_paths=_artifact_paths(record),
        used_model=used_model,
        status="built",
    )


def compact_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    marker = "\n...[context compacted by structured budget]...\n"
    if max_chars <= len(marker) + 4:
        return (text[: max(0, max_chars - len(marker))] + marker)[:max_chars]
    content_budget = max_chars - len(marker)
    if content_budget < 240:
        tail_budget = max(1, content_budget // 2)
    else:
        tail_budget = max(80, content_budget // 3)
    head_budget = max(0, content_budget - tail_budget)
    return text[:head_budget].rstrip() + marker + text[-tail_budget:].lstrip()


def _command_summary(command: str, returncode: int, stdout: str, stderr: str) -> str:
    detail = (stderr or stdout).strip()
    if len(detail) > 1200:
        detail = _summarize_long_command_output(detail)
    return f"{command} -> {returncode}\n{detail}"


def _summarize_long_command_output(detail: str) -> str:
    keywords = (
        "error",
        "failed",
        "failure",
        "assert",
        "cannot find",
        "not found",
        "traceback",
        "panic",
    )
    interesting = []
    for line in detail.splitlines():
        lower = line.lower()
        if any(keyword in lower for keyword in keywords):
            interesting.append(line.strip())
        if len(interesting) >= 10:
            break
    if interesting:
        return "\n".join(interesting) + "\n...[command output summarized; full log remains in artifacts]..."
    return compact_text(detail, 1200)


def _raw_context(record: RunRecord) -> str:
    parts = [
        f"Task: {record.task}",
        f"Range: {record.git_range}",
        "Changed files:",
        "\n".join(f"- {item.status}\t{item.path}" for item in record.changed_files),
        "Context summary:",
        record.context_summary,
        "Commands:",
        "\n".join(_command_summary(item.command, item.returncode, item.stdout, item.stderr) for item in record.commands),
    ]
    if record.diff_index_path and record.diff_index_path.exists():
        parts.extend(["Diff index:", record.diff_index_path.read_text(encoding="utf-8", errors="replace")])
    return redact_secrets("\n\n".join(parts))


def _structured_context_summary(record: RunRecord) -> str:
    lines = [
        "# Structured Run Memory",
        "",
        "- Mode: structured",
        f"- Run: `{record.run_id}`",
        f"- Git range: `{record.git_range}`",
        f"- Context strategy: `{record.context_strategy or 'unknown'}`",
        "- Rule: keep changed files, diff index, risk summary, command log summaries, and artifact paths.",
        "- Rule: do not use final head-only truncation; large raw diff/log content stays in artifacts for tool readback.",
        "",
        "## Changed Files",
    ]
    for item in record.changed_files:
        lines.append(f"- {item.status}\t{item.path}")
    lines.extend(["", "## Context Artifacts"])
    for path in _artifact_paths(record):
        try:
            rendered = path.relative_to(record.run_dir)
        except ValueError:
            rendered = path
        lines.append(f"- `{rendered}`")
    lines.extend(["", "## Tool And Command Summary"])
    if record.agent_turns:
        for turn in record.agent_turns:
            lines.append(f"- turn {turn.turn}: `{turn.tool}` -> {turn.output_summary}")
    elif record.tools_used:
        for tool in record.tools_used:
            lines.append(f"- `{tool}`")
    if record.commands:
        lines.extend(["", "## Command Results"])
        for command in record.commands:
            lines.append(f"- `{command.command}` -> exit {command.returncode}; log `{command.log_path.relative_to(record.run_dir)}`")
    return "\n".join(lines) + "\n"


def _artifact_paths(record: RunRecord) -> list[Path]:
    paths: list[Path] = []
    for candidate in (record.diff_index_path, record.context_dir / "changed-files.json" if record.context_dir else None):
        if candidate and candidate.exists():
            paths.append(candidate)
    if record.context_dir:
        diffs = record.context_dir / "diffs"
        if diffs.exists():
            paths.extend(sorted(item for item in diffs.rglob("*.diff") if item.is_file()))
    paths.extend(command.log_path for command in record.commands if command.log_path.exists())
    return paths


def _model_context_summary(raw_context: str) -> tuple[str | None, bool]:
    from ..agent.config import configure_agents_sdk, model_provider_from_env

    provider = model_provider_from_env()
    if not provider.available:
        return None, False
    try:
        from agents import Agent, Runner
    except ImportError:
        return None, False
    if not configure_agents_sdk(provider):
        return None, False
    agent = Agent(
        name="AI Test Officer Context Summarizer",
        instructions=load_prompt("context_summarizer"),
        model=provider.model,
    )
    try:
        result = Runner.run_sync(agent, raw_context)
    except Exception:
        return None, False
    return str(getattr(result, "final_output", result)), True
