# Codex SDK Notes

Official Codex manual section used for this MVP: [Codex SDK](https://developers.openai.com/codex/sdk).

## Python SDK

- Package: `openai-codex`
- Import path: `openai_codex`
- Requires Python 3.10 or later.
- The Python SDK controls the local Codex app-server over JSON-RPC.
- Published SDK builds include a pinned Codex CLI runtime dependency.

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

## Sandbox Presets

The MVP exposes these SDK presets:

- `read_only`: inspect only.
- `workspace_write`: read files and write in the workspace.
- `full_access`: no filesystem sandbox restrictions.

Default is `workspace_write`, but the prompt forbids source edits unless `--allow-edits` is passed.

