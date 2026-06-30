# T Test Agent

AI Test Officer MVP for the hackathon direction `AI 测试官`.

Competition target: build an Agent that completes the loop
`understand change -> plan test strategy -> execute validation -> write a decision-ready report`,
covering backend logic and, later, frontend experience. The detailed requirement
breakdown lives in [docs/competition-requirements.md](docs/competition-requirements.md).

The first version keeps the product thin and lets Codex do the heavy lifting:

- read code / requirements / diffs,
- infer risk and test scope,
- plan useful checks,
- run validation through the local Codex runtime,
- write a decision-ready Markdown report.

## Tech Stack

- Python: `3.12`, pinned in `.python-version`.
- Package and environment manager: `uv 0.11.25`.
- Backend: Python first. The MVP exposes a CLI and report generator before adding service APIs.
- Frontend: deferred. A lightweight report UI is useful for the final competition demo, but it is not required for the first backend MVP.

## Setup

```powershell
winget install --id astral-sh.uv -e
uv sync --extra codex --group dev
```

This project uses `uv` for Python version, virtual environment, dependency, and lockfile management.
The `codex` extra installs the official Python package `openai-codex`, which controls the local Codex app-server.

For company-internal runs, copy `.env.example` to `.env` and fill local tokens.
The project-level Codex MCP template lives in `.codex/config.toml`; it references
environment variables only and does not contain secrets.

## Usage

Preview the prompt without calling Codex:

```powershell
uv run ai-test-officer prompt --task "Review this repo and propose the first MVP test plan."
```

Generate a dry-run report:

```powershell
uv run ai-test-officer run --task "Review this repo and propose the first MVP test plan." --dry-run
```

Check internal integrations without printing secrets:

```powershell
uv run ai-test-officer doctor
```

Simulate a WeCom bot notification without sending:

```powershell
uv run ai-test-officer notify --message "AI Test Officer notify smoke" --dry-run
```

Create and run the synthetic A/B/C competition demos:

```powershell
uv run ai-test-officer scenario create --scenario all --demo-root /tmp/ai-test-officer-scenarios
uv run ai-test-officer scenario run --scenario A --demo-root /tmp/ai-test-officer-scenarios --dry-run
uv run ai-test-officer scenario run --scenario A-fullstack --demo-root /tmp/ai-test-officer-scenarios --dry-run --visualize
uv run ai-test-officer scenario run --scenario B --demo-root /tmp/ai-test-officer-scenarios --dry-run
uv run ai-test-officer scenario run --scenario C --demo-root /tmp/ai-test-officer-scenarios --dry-run
```

For the full-chain browser demo, install the optional Playwright extra and Chromium:

```powershell
uv sync --extra codex --extra e2e --group dev
uv run python -m playwright install chromium
```

The synthetic fullstack repo also works as a standalone demo because its browser
test command uses `uv run --with playwright ...`.

Send a report to a WeCom group bot after setting `WECOM_WEBHOOK_KEY` in local
`.env` or the full `WECOM_WEBHOOK_URL`:

```powershell
uv run ai-test-officer notify --report reports/latest-report.md --message "场景A测试报告"
```

The scenario runner can also push the generated report summary:

```powershell
uv run ai-test-officer scenario run --scenario A --demo-root /tmp/ai-test-officer-scenarios --send
```

Generate the static visual report used for the competition demo:

```powershell
uv run ai-test-officer scenario create --scenario A-fullstack --demo-root /tmp/ai-test-officer-scenarios
uv run ai-test-officer scenario run --scenario A-fullstack --demo-root /tmp/ai-test-officer-scenarios --visualize
```

Run scenario A against the last local commit:

```powershell
uv run ai-test-officer run --repo . --last-commit --task "场景A：分析刚提交的改动并跑针对性测试"
```

Run scenario A against a specific local git range:

```powershell
uv run ai-test-officer run --repo . --git-range "main..HEAD" --task "场景A：分析这个分支改动并跑针对性测试"
```

Run through the Codex Python SDK:

```powershell
uv run ai-test-officer run --task "Analyze the latest changes, run safe checks, and produce a test report."
```

Codex SDK runs use ephemeral threads by default, so they should not stay in the
Codex sidebar. When debugging and intentionally keeping the thread, pass
`--save-thread`.

Reports are written to `reports/latest-report.md` by default. Each run also
writes a JSON sidecar next to the report. Render it as a static HTML page with:

```powershell
uv run ai-test-officer visualize --report reports/latest-report.md
```

## Scenario A Demo

Create synthetic demo repositories:

```powershell
uv run python scripts/create_scenario_demos.py
```

Or create only the scenario A repository with a baseline commit followed by a
buggy checkout change:

```powershell
uv run python scripts/create_scenario_a_demo.py
```

The script prints the generated repository path and ready-to-run `scenario`
commands:

```powershell
uv run ai-test-officer scenario run --scenario A --demo-root <demo-root> --dry-run
```

The demo uses Python `unittest` and intentionally breaks an existing boundary
test so the report can explain the changed file, risk, failing validation, and
recommended fix.

## Verification

```powershell
uv run ruff check .
uv run python -m unittest discover -s tests -p 'test_*.py' -v
```

Before committing, verify the lockfile and environment:

```powershell
uv lock --check
uv sync --locked --extra codex --group dev
```

## Current MVP Scope

- Python CLI wrapper around the Codex Python SDK.
- Structured Test Officer prompt.
- Markdown report writer.
- Local dry-run mode for prompt and report iteration.
- Scenario A local git diff workflow for `--last-commit` and `--git-range`.
- Scenario A/B/C synthetic competition demos through `scenario create/run`.
- Scenario A-fullstack demo for backend logic, HTTP API, browser validation, and screenshot evidence.
- JSON sidecar and static HTML visual report generation.
- Internal integration doctor for TAPD, iWiki, Gongfeng/TGit, and Playwright MCP.
- WeCom bot notification dry-run and optional webhook delivery.
- Repo skill under `.agents/skills/ai-test-officer` for the reusable competition workflow.
- Docs for competition requirements, architecture, and SDK notes.

Next milestones should add MR diff adapters, real TAPD requirement context,
scheduled checks, and optional bot intake.

For company-internal demo setup, including TAPD and TGit configuration, see
[docs/internal-integrations.md](docs/internal-integrations.md).

## Frontend Plan

The competition does not require a frontend, but it encourages graphical or real-time presentation of the testing process and results. This repo now uses a static HTML report as the lightweight presentation layer. It shows the test timeline, changed files, risk level, failures, screenshots, and final verdict without requiring a long-running web service.

## Data Strategy

Do not commit real business code, private PR diffs, logs, screenshots, traces, or requirement documents to this public repository.

Use three data tiers:

1. Synthetic demo data in this repo: small sample diffs, fake requirements, seeded bugs, and safe test outputs.
2. Sanitized internal examples: only if the team has authorization, remove sensitive paths, names, tokens, customer data, and business details.
3. Live local evaluation: point the agent at an authorized local or internal repository at runtime, then keep generated reports and evidence out of git unless they are fully sanitized.

For the competition demo, the strongest path is to prepare a small reproducible demo repo with known defects, then optionally show one authorized team-code run locally to prove the workflow transfers to real development code.

## GitHub Sync

After each code change, run the verification commands. If they pass, commit and push the update to `origin/main`:

```powershell
git status --short
git add .
git commit -m "<change summary>"
git push
```
