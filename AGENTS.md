# Repository Instructions

- Keep the MVP small and runnable from a clean checkout.
- Prefer standard-library Python unless a dependency directly supports the Codex/Test Officer workflow.
- Do not commit secrets, tokens, real business data, traces, screenshots, or private logs.
- Use `$env:PYTHONPATH='src'; python -m unittest discover -s tests -p 'test_*.py'` as the baseline verification command on Windows.
- Reports under `reports/` are generated artifacts; keep only `.gitkeep` by default.
