# T Test Agent

AI Test Officer MVP for the hackathon direction `AI 测试官`.

The first version keeps the product thin and lets Codex do the heavy lifting:

- read code / requirements / diffs,
- infer risk and test scope,
- plan useful checks,
- run validation through the local Codex runtime,
- write a decision-ready Markdown report.

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

## GitHub Sync

After each code change, run the verification commands. If they pass, commit and push the update to `origin/main`:

```powershell
git status --short
git add .
git commit -m "<change summary>"
git push
```
