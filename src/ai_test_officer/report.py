from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .models import TestTask


def write_report(task: TestTask, body: str, dry_run: bool = False) -> Path:
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
    return output_path


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

