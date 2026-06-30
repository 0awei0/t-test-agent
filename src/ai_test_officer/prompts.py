from __future__ import annotations

from pathlib import Path

from .models import TestTask


MAX_CONTEXT_CHARS = 12_000


def build_test_officer_prompt(task: TestTask) -> str:
    """Build the instruction sent to Codex for a single test-officer run."""

    repo = task.resolved_repo()
    edit_policy = (
        "You may edit files when needed to create or improve tests."
        if task.allow_edits
        else "Do not edit source files. You may inspect files and run safe commands only."
    )
    context_blocks = [
        _text_context("Changed Files", task.changed_files, task.diff_label),
        _text_context("Git diff", task.diff_text, task.diff_label),
        _file_context("PR diff", task.diff_path),
        _file_context("Requirement", task.requirement_path),
    ]
    context = "\n\n".join(block for block in context_blocks if block)
    scenario_a = _scenario_a_instructions(task)

    return f"""You are AI Test Officer, a full-chain testing agent.

Repository: {repo}
Task: {task.task}
Use $ai-test-officer when available.

Operating policy:
- {edit_policy}
- Prefer existing project commands and tests before inventing new ones.
- If the project has no tests yet, propose the smallest useful first test surface.
- If a web UI or browser path is present, validate it with Playwright MCP when available.
- If Playwright MCP is unavailable, run the repository's Playwright/browser test command instead.
- For lightweight demo repos, use `uv run --with playwright ...` before concluding Playwright is unavailable.
- Save browser screenshots or evidence under `reports/evidence/` and reference them in the report.
- When running commands, record what was run and what the result means.
- Do not use real sensitive data. Do not expose secrets.

Workflow:
1. Understand the request, changed surface, and likely risk areas.
2. Inspect the repository structure and relevant files.
3. Produce a compact test strategy before execution.
4. Run safe validation where available.
5. Explain failures with likely causes and next actions.

{scenario_a}

Final response format:
# AI Test Officer Report

## Summary
- Verdict: pass | fail | needs-follow-up
- Risk: low | medium | high
- One-paragraph decision summary.

## Scope
- What was inspected.
- What was not inspected and why.

## Changed Files / Risk Map
- Changed files and risk areas.

## Test Strategy
- Planned checks and reasoning.

## Execution
- Commands or checks run.
- Results and evidence.

## Findings
- Issues, suspected causes, and reproduction notes.

## Recommended Next Steps
- Prioritized follow-up actions.

{context}
"""


def _file_context(label: str, path: Path | None) -> str:
    if path is None:
        return ""

    resolved = path.expanduser().resolve()
    if not resolved.exists():
        return f"## {label} Input\nPath was provided but does not exist: {resolved}"

    text = resolved.read_text(encoding="utf-8", errors="replace")
    truncated = text[:MAX_CONTEXT_CHARS]
    suffix = "\n\n[truncated]" if len(text) > MAX_CONTEXT_CHARS else ""
    return f"## {label} Input\nPath: {resolved}\n\n```text\n{truncated}{suffix}\n```"


def _text_context(label: str, text: str | None, source: str | None = None) -> str:
    if not text:
        return ""

    truncated = text[:MAX_CONTEXT_CHARS]
    suffix = "\n\n[truncated]" if len(text) > MAX_CONTEXT_CHARS else ""
    source_line = f"\nSource: {source}" if source else ""
    return f"## {label} Input{source_line}\n\n```text\n{truncated}{suffix}\n```"


def _scenario_a_instructions(task: TestTask) -> str:
    if not task.has_change_context():
        return ""

    return """Scenario A mode:
- Treat the provided diff as a developer's just-submitted code change.
- Infer the change intent from the diff and surrounding repository context.
- Build a changed-files risk map before choosing tests.
- Run targeted existing tests or safe validation commands that match the risk.
- Give feedback directly to the developer with reproduction notes and next actions."""
