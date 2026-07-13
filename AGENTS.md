# Repository Instructions

## Project Shape

- Keep the MVP small and runnable from a clean checkout.
- Prefer standard-library Python unless a dependency directly supports the Codex/Test Officer workflow.
- Do not commit secrets, tokens, real business data, traces, screenshots, or private logs.
- Reports under `reports/` are generated artifacts; keep only `.gitkeep` by default.

## Environment

- Use `uv` for environment and dependency management.
- Run `uv sync --locked --group dev` after Python dependency changes.
- Keep `uv.lock` committed whenever dependency metadata changes.
- Use `uv run ...` for local commands instead of activating `.venv` manually.

## Verification

- Run `uv lock --check` after dependency metadata changes.
- Run `uv run ruff check .` before committing code.
- Run `uv run python -m unittest discover -s agents-sdk-agent/tests -p 'test_*.py' -v` before committing code.
- Run `npm --prefix frontend run typecheck` and `npm --prefix frontend run build` after frontend changes.

## GitHub Sync

- After every code change, update tests or docs as needed.
- Only commit after the relevant tests pass.
- After tests pass, commit the change and push it to `origin/main` on GitHub.
