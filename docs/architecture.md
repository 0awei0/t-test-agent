# AI Test Officer MVP Architecture

## Goal

Build the smallest useful demo for the hackathon's `AI 测试官` direction: a Codex-powered testing agent that can understand a testing request, inspect a repo, plan checks, run safe validation, and produce a decision-ready report.

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

## MVP Boundaries

- Use Codex built-in code understanding, shell execution, and local project context.
- Do not build custom tool orchestration or memory yet.
- Store report history as files first; move to a database only when the demo needs search or dashboards.
- Keep TGit/TAPD/bot integrations as second-stage adapters.
- Prefer dry-run prompt iteration before allowing Codex to modify files.

## Planned Milestones

1. Python CLI wrapper and report writer.
2. Codex SDK execution path.
3. Playwright evidence capture for one local web app.
4. GitHub PR diff input.
5. Scheduled smoke checks.
6. Webhook/bot report delivery.

