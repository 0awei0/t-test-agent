from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class CodexDependencyError(RuntimeError):
    """Raised when the optional Codex SDK dependency is missing."""


@contextmanager
def pushd(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class CodexRunner:
    """Small adapter around the official `openai-codex` Python SDK."""

    def __init__(self, model: str | None = None, sandbox: str = "workspace_write") -> None:
        self.model = model or os.getenv("AI_TEST_OFFICER_MODEL", "gpt-5.4")
        self.sandbox = sandbox

    def run(self, prompt: str, repo_path: Path) -> str:
        try:
            from openai_codex import Codex, Sandbox
        except ImportError as exc:
            raise CodexDependencyError(
                "Missing optional dependency `openai-codex`. "
                "Install it with: python -m pip install -e \".[codex]\""
            ) from exc

        sandbox = self._sandbox_value(Sandbox)
        with pushd(repo_path):
            with Codex() as codex:
                thread = codex.thread_start(model=self.model, sandbox=sandbox)
                result = thread.run(prompt)

        final_response = getattr(result, "final_response", None)
        return final_response if final_response is not None else str(result)

    def _sandbox_value(self, sandbox_cls: object) -> object:
        mapping = {
            "read_only": "read_only",
            "workspace_write": "workspace_write",
            "full_access": "full_access",
        }
        attr = mapping.get(self.sandbox)
        if attr is None:
            allowed = ", ".join(mapping)
            raise ValueError(f"Unsupported sandbox `{self.sandbox}`. Choose one of: {allowed}.")
        return getattr(sandbox_cls, attr)

