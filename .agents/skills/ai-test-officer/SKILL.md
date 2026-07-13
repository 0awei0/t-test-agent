---
name: ai-test-officer
description: Run the AI Test Officer workflow for PR or TAPD-driven testing. Use when asked for AI 测试官, PR/MR test reports, TAPD bug/story analysis, Gongfeng/TGit MR diff testing, competition demo preparation, or a decision-ready validation report from code changes and requirements.
---

# AI Test Officer

## Overview

Use this skill to turn a simple testing request, Gongfeng/TGit MR, TAPD item, or
local diff into a scoped test strategy and report. The active implementation is
the Agents SDK version under `agents-sdk-agent/`; the previous Codex SDK version
is archived under `codex-agent/`.

## Workflow

1. Gather available inputs:
   - Gongfeng/TGit MR URL or local diff file.
   - Local git diff via `--git-range <base>..<head>`.
   - TAPD story, task, or bug ID when provided.
   - Local repository path that is authorized for inspection.
2. Prefer deterministic adapters for automation:
   - Use Gongfeng REST for scripted MR metadata and diff fetches.
   - Use MCP tools for interactive Codex exploration when they are available.
3. Save fetched context into generated local files outside git-tracked fixtures.
4. Run the active Agents SDK report path:

   ```bash
   uv run ai-test-officer run \
     --repo <repo> \
     --git-range <base>..<head> \
     --task "<testing request>" \
   ```
   To allow generated temporary test code in the isolated run workspace:

   ```bash
   uv run ai-test-officer run \
     --repo <repo> \
     --git-range <base>..<head> \
     --allow-temp-test-code \
     --task "<testing request>"
   ```
   Outputs are written under `runs/<run-id>/`.
5. If the user wants a WeCom notification, pass `--send`. Use
   `--notify-dry-run` first when validating payload shape.
6. For model-backed summaries, load local `.env` before running. OpenAI uses
   `OPENAI_API_KEY`; Doubao/Volcengine Ark can use:

   ```bash
   ARK_API_KEY=<local-only>
   AI_TEST_OFFICER_MODEL=doubao-seed-2-1-turbo-260628
   AI_TEST_OFFICER_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
   AI_TEST_OFFICER_OPENAI_API=chat_completions
   AI_TEST_OFFICER_DISABLE_TRACING=true
   ```
7. For browser evidence, install the optional e2e extra and Chromium:

   ```bash
   uv sync --extra e2e --group dev
   uv run python -m playwright install chromium
   ```
   In synthetic demo repos, prefer `uv run --with playwright python -m unittest ...`
   so the browser test has its dependency even outside this project venv.
8. To verify the configured model can call local Agents SDK tools:

   ```bash
   uv run ai-test-officer smoke tools --run-id doubao-tool-smoke
   ```
9. For the competition judging demo, use `release-guard` as the primary flow:

   ```bash
   uv run ai-test-officer demo showcase \
     --scenario release-guard \
     --demo-root runs/demos \
     --runs-root runs/showcase \
     --planner-mode agent-strict \
     --run-id release-guard-showcase \
     --export-fue runs/edgeone-site/release-guard-showcase \
     --notify-dry-run
   ```

   Deploy the generated static project through EdgeOne Makers, then rerun with
   `--detail-url` and `--send` so WeCom only carries the summary and link.
   Keep `agent-loop` as the fast fallback when a short, stable tool-loop demo is needed.

## Guardrails

- Do not print tokens or copy token values into reports, prompts, commits, or logs.
- Do not commit `.env`, `.mcp.json`, real PR diffs, TAPD content, screenshots, or generated reports.
- Do not commit or print WeCom webhook URLs, `WECOM_WEBHOOK_URL`, or `WECOM_WEBHOOK_KEY`.
- Keep demo data synthetic or sanitized unless the user explicitly authorizes a local internal run.
- For real MR testing, only read the MR diff or simulate it in a local run workspace under `runs/`.
- Never commit, push, merge, rebase, checkout, switch branches, reset, clean, stash, comment on an MR,
  or otherwise mutate the original business repository or remote MR state.
- Feature-environment routing must match the single authorized local test environment.
  Never use another person's `customPath`, environment name, or environment id. If a tool
  or model proposes an unapproved environment, stop and report the policy violation.
- Generated test code is allowed only inside `runs/<run-id>/repo/` and only when
  `--allow-temp-test-code` is passed.
- If MCP tools are missing in the current thread, tell the user to restart Codex or open a new thread so project `.codex/config.toml` and repo skills are reloaded.

## Tool Choice

- Treat Gongfeng and TGit as one Git/MR platform capability.
- Use Gongfeng REST for repeatable Python automation and CI-like checks.
- Use TGit MCP when Codex needs interactive MR, repository, or file context.
- Use TAPD MCP for bug/story/task context.
- Use Playwright MCP when browser interaction or screenshot evidence is needed.
- If Playwright MCP is unavailable, run the repository's local Playwright tests as a stable fallback.
- Use WeCom outbound webhook only for report notification in the current MVP.

## Local Test Execution

- The active MVP has a deterministic planner plus optional Agents SDK summary.
- The deterministic planner chooses safe local test commands from changed files.
- The showcase path uses `agent-strict` to prove a multi-turn tool loop. It should
  show changed-file reading, diff reading, temporary test writing, test execution,
  log reading on failure, and the final report.
- Temporary generated test code is only written under `runs/<run-id>/repo/` and
  only when `--allow-temp-test-code` is set.
- The current Python demo-specific generated test is a conservative seed rule,
  not a business-repo mutation. Replace or extend it through tools when the
  Agents SDK planning loop grows.

## Code Organization

- `agent/`: model provider setup, Agents SDK summary, tool-call smoke.
- `tools/`: read-only git helpers, safe local command/write tools.
- `execution/`: isolated workspace creation and run orchestration.
- `memory/`: local prompt/context compaction.
- `skill/`: repo skill instruction loading.
- `mcp/`: project MCP config loading and future MCP adapters.
- `integrations/`: WeCom and other outbound integrations.
