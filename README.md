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
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[codex,dev]"
```

The `codex` extra installs the official Python package `openai-codex`, which controls the local Codex app-server.

## Usage

Preview the prompt without calling Codex:

```powershell
python -m ai_test_officer prompt --task "Review this repo and propose the first MVP test plan."
```

Generate a dry-run report:

```powershell
python -m ai_test_officer run --task "Review this repo and propose the first MVP test plan." --dry-run
```

Run through the Codex Python SDK:

```powershell
python -m ai_test_officer run --task "Analyze the latest changes, run safe checks, and produce a test report."
```

Reports are written to `reports/latest-report.md` by default.

## Verification

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -p 'test_*.py'
```

## Current MVP Scope

- Python CLI wrapper around the Codex Python SDK.
- Structured Test Officer prompt.
- Markdown report writer.
- Local dry-run mode for prompt and report iteration.
- Docs for competition requirements, architecture, and SDK notes.

Later milestones should add Playwright evidence capture, GitHub PR diff input, scheduled checks, and bot/webhook delivery.
