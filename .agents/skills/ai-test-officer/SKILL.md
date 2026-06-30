---
name: ai-test-officer
description: Run the AI Test Officer workflow for PR or TAPD-driven testing. Use when asked for AI 测试官, PR/MR test reports, TAPD bug/story analysis, Gongfeng/TGit MR diff testing, competition demo preparation, or a decision-ready validation report from code changes and requirements.
---

# AI Test Officer

## Overview

Use this skill to turn a simple testing request, Gongfeng/TGit MR, TAPD item, or
local diff into a scoped test strategy and Markdown report.

## Workflow

1. Run `uv run ai-test-officer doctor` before using company integrations.
2. Gather available inputs:
   - Gongfeng/TGit MR URL or local diff file.
   - Local git diff via `--last-commit` or `--git-range <base>..<head>`.
   - TAPD story, task, or bug ID when provided.
   - Local repository path that is authorized for inspection.
3. Prefer deterministic adapters for automation:
   - Use Gongfeng REST for scripted MR metadata and diff fetches.
   - Use MCP tools for interactive Codex exploration when they are available.
4. Save fetched context into generated local files outside git-tracked fixtures.
5. Run the report path:

   ```bash
   uv run ai-test-officer run \
     --task "<testing request>" \
     --repo <repo> \
     --last-commit \
     --requirement <generated-or-local-requirement> \
     --output reports/latest-report.md
   ```
   SDK runs use ephemeral Codex threads by default. Add `--save-thread` only
   when you need to inspect the SDK conversation in the Codex sidebar.
6. Optionally simulate or send the report through a WeCom group bot:

   ```bash
   uv run ai-test-officer notify \
     --report reports/latest-report.md \
     --message "AI Test Officer report" \
     --dry-run
   ```
7. For competition scenario demos, create synthetic A/B/C repos and run them
   through the scenario CLI:

   ```bash
   uv run ai-test-officer scenario create --scenario all --demo-root /tmp/ai-test-officer-scenarios
   uv run ai-test-officer scenario run --scenario A --demo-root /tmp/ai-test-officer-scenarios --dry-run
   uv run ai-test-officer scenario run --scenario A-fullstack --demo-root /tmp/ai-test-officer-scenarios --visualize
   uv run ai-test-officer scenario run --scenario B --demo-root /tmp/ai-test-officer-scenarios --dry-run
   uv run ai-test-officer scenario run --scenario C --demo-root /tmp/ai-test-officer-scenarios --dry-run
   ```
8. For browser evidence, install the optional e2e extra and Chromium:

   ```bash
   uv sync --extra codex --extra e2e --group dev
   uv run python -m playwright install chromium
   ```
   In synthetic demo repos, prefer `uv run --with playwright python -m unittest ...`
   so the browser test has its dependency even outside this project venv.

## Guardrails

- Do not print tokens or copy token values into reports, prompts, commits, or logs.
- Do not commit `.env`, `.mcp.json`, real PR diffs, TAPD content, screenshots, or generated reports.
- Do not commit or print WeCom webhook URLs, `WECOM_WEBHOOK_URL`, or `WECOM_WEBHOOK_KEY`.
- Keep demo data synthetic or sanitized unless the user explicitly authorizes a local internal run.
- If MCP tools are missing in the current thread, tell the user to restart Codex or open a new thread so project `.codex/config.toml` and repo skills are reloaded.

## Tool Choice

- Treat Gongfeng and TGit as one Git/MR platform capability.
- Use Gongfeng REST for repeatable Python automation and CI-like checks.
- Use TGit MCP when Codex needs interactive MR, repository, or file context.
- Use TAPD MCP for bug/story/task context.
- Use Playwright MCP when browser interaction or screenshot evidence is needed.
- If Playwright MCP is unavailable, run the repository's local Playwright tests as a stable fallback.
- Use WeCom outbound webhook only for report notification in the current MVP.
