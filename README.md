# T Test Agent

AI Test Officer MVP for the hackathon direction `AI 测试官`.

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

## Usage

Preview the prompt without calling Codex:

```powershell
uv run ai-test-officer prompt --task "Review this repo and propose the first MVP test plan."
```

Generate a dry-run report:

```powershell
uv run ai-test-officer run --task "Review this repo and propose the first MVP test plan." --dry-run
```

Run through the Codex Python SDK:

```powershell
uv run ai-test-officer run --task "Analyze the latest changes, run safe checks, and produce a test report."
```

Reports are written to `reports/latest-report.md` by default.

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
- Docs for competition requirements, architecture, and SDK notes.

Later milestones should add Playwright evidence capture, GitHub PR diff input, scheduled checks, and bot/webhook delivery.

## Frontend Plan

The competition does not require a frontend, but it does encourage graphical or real-time presentation of the testing process and results. For the MVP, Markdown reports are enough to prove the agent loop. Before submission, add one lightweight presentation layer:

- static HTML report generated from Markdown, or
- a small Python web UI, such as FastAPI plus a simple template, or
- a local dashboard that shows test timeline, changed files, risk level, failures, screenshots, and final verdict.

Avoid building a full product console until the core testing workflow is reliable.

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
