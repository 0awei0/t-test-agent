# Codex SDK Notes

Official Codex manual section used for this MVP: [Codex SDK](https://developers.openai.com/codex/sdk).

## Python SDK

- Package: `openai-codex`
- Import path: `openai_codex`
- Requires Python 3.10 or later.
- The Python SDK controls the local Codex app-server over JSON-RPC.
- Published SDK builds include a pinned Codex CLI runtime dependency.

## Version Pin

The `codex` extra pins `openai-codex==0.1.0b3`.

Do not downgrade to `0.1.0b2` in this Linux demo environment. That SDK build
pins `openai-codex-cli-bin==0.132.0`, which does not publish a manylinux
`x86_64` wheel. `0.1.0b3` pins `openai-codex-cli-bin==0.137.0a4`, which does.

Because the SDK and CLI binary are beta/pre-release packages, `pyproject.toml`
sets `tool.uv.prerelease = "allow"` so `uv lock` and `uv sync` work without
extra command-line flags.

Minimal official-style usage:

```python
from openai_codex import Codex, Sandbox

with Codex() as codex:
    thread = codex.thread_start(
        model="gpt-5.4",
        sandbox=Sandbox.workspace_write,
    )
    result = thread.run("Make a plan to diagnose and fix the CI failures")
    print(result.final_response)
```

## Why This MVP Uses The SDK Directly

- It is lighter than building an MCP or plugin layer first.
- It lets us validate the core product loop early: request -> Codex testing work -> report.
- It keeps future paths open: the same flow can later become a Skill, plugin, GitHub Action, or service worker.

## Thread Storage

The SDK creates Codex threads in the local app-server. To avoid polluting the
Codex sidebar during repeated test-agent runs, this project starts SDK threads
with `ephemeral=True` by default.

Configuration:

- `AI_TEST_OFFICER_CODEX_EPHEMERAL=true`: default; do not keep SDK runs as saved sidebar threads.
- `AI_TEST_OFFICER_CODEX_AUTO_ARCHIVE=true`: archive non-ephemeral SDK threads after a run.
- `--save-thread`: CLI escape hatch for debugging; keeps the SDK thread visible.

Use `--save-thread` only when investigating a Codex SDK behavior and you want to
inspect the conversation in the app.

## Sandbox Presets

The MVP exposes these SDK presets:

- `read_only`: inspect only.
- `workspace_write`: read files and write in the workspace.
- `full_access`: no filesystem sandbox restrictions.

Default is `workspace_write`, but the prompt forbids source edits unless `--allow-edits` is passed.
