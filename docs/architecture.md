# AI Test Officer MVP Architecture

## Goal

Build the smallest useful demo for the hackathon's `AI 测试官` direction: a Codex-powered testing agent that can understand a testing request, inspect a repo, plan checks, run safe validation, and produce a decision-ready report.

The backend is Python-first for the current phase. Frontend work is intentionally deferred until the test workflow, report schema, and evidence capture are stable.

## Shape

```text
User / Scheduler / PR trigger
        |
        v
Python CLI: ai-test-officer
        |
        v
Prompt builder + local inputs
        |
        v
Codex Python SDK -> local Codex app-server/runtime
        |
        v
Repo inspection, command execution, optional test edits
        |
        v
Markdown report under reports/
```

Later, the report output can feed a thin UI:

```text
Markdown / JSON report
        |
        v
Static HTML or small Python web UI
        |
        v
Timeline, risk, findings, screenshots, logs, and verdict
```

## MVP Boundaries

- Use Codex built-in code understanding, shell execution, and local project context.
- Do not build custom tool orchestration or memory yet.
- Store report history as files first; move to a database only when the demo needs search or dashboards.
- Keep TGit/TAPD/bot integrations as second-stage adapters.
- Prefer dry-run prompt iteration before allowing Codex to modify files.
- Keep all committed demo data synthetic or sanitized.
- Run against real team code only in an authorized local or internal environment.

## Planned Milestones

1. Python CLI wrapper and report writer.
2. Codex SDK execution path.
3. Playwright evidence capture for one local web app.
4. GitHub PR diff input.
5. Scheduled smoke checks.
6. Webhook/bot report delivery.
