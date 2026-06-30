# AI Test Officer MVP Architecture

## Goal

Build the smallest useful demo for the hackathon's `AI 测试官` direction: a Codex-powered testing agent that can understand a testing request, inspect a repo, plan checks, run safe validation, and produce a decision-ready report.

The backend is Python-first for the current phase. Frontend work is intentionally deferred until the test workflow, report schema, and evidence capture are stable.

The competition target is a full loop, not a script runner:

```text
simple instruction
        |
        v
understand change / requirement / online signal
        |
        v
plan targeted validation strategy
        |
        v
execute backend, API, browser, or patrol checks
        |
        v
decision-ready report and optional bot notification
```

## Shape

```text
User / Scheduler / PR trigger
        |
        v
Python CLI: ai-test-officer
        |
        v
Prompt builder + local inputs / local git diff adapter / scenario runner
        |
        v
Codex Python SDK -> local Codex app-server/runtime
        |
        v
Repo inspection, command execution, optional test edits
        |
        v
Markdown report + JSON sidecar under reports/
```

The report output feeds a thin static visual report:

```text
Markdown / JSON report
        |
        v
Static HTML report
        |
        v
Timeline, risk, findings, screenshots, logs, and verdict
```

## MVP Boundaries

- Use Codex built-in code understanding, shell execution, and local project context.
- Prioritize Scenario A first: local commit or MR diff -> targeted test report.
- Treat Scenario B and C as follow-up adapter work, not separate products.
- Do not build custom long-term memory yet.
- Store report history as files first; move to a database only when the demo needs search or dashboards.
- Keep TGit/TAPD/Playwright/bot integrations behind small adapters and doctor checks.
- Prefer dry-run prompt iteration before allowing Codex to modify files.
- Keep all committed demo data synthetic or sanitized.
- Run against real team code only in an authorized local or internal environment.

## Planned Milestones

1. Python CLI wrapper and report writer. Done.
2. Codex SDK execution path. Done.
3. Scenario A local git diff input (`--last-commit`, `--git-range`). Done.
4. Integration doctor for TAPD, iWiki, Gongfeng/TGit, and Playwright MCP. Done.
5. WeCom bot dry-run and optional report delivery. Done.
6. Synthetic A/B/C scenario commands. Done.
7. A-fullstack demo with backend, API, browser, and screenshot evidence. Done.
8. Static HTML visual report page for judging and demo presentation. Done.
9. Gongfeng/TGit MR diff input for real Scenario A runs.
10. TAPD requirement and bug context for real Scenario B runs.
11. Scheduled smoke checks for Scenario C.

## Competition Fit

| Requirement | MVP answer | Remaining work |
| --- | --- | --- |
| Simple testing instruction | `ai-test-officer run --task ...` | Add presets for common team workflows. |
| Understand changed code | Local git diff prompt context | Add Gongfeng/TGit MR adapter. |
| Plan strategy | Codex prompt requires risk map and selected checks | Refine structured plan extraction. |
| Execute validation | Codex SDK can run local tests; A-fullstack includes browser evidence | Add real team app E2E paths later. |
| Report for human decision | Markdown, JSON sidecar, and static HTML visual report | Add richer live dashboard only if needed. |
| Notify developers/on-call | WeCom outbound `notify` and scenario `--send` | Inbound group Q&A is deferred. |
| Scheduled patrol | Not in MVP | Add timer/cron wrapper after stable checks exist. |
