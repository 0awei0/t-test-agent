from __future__ import annotations

from importlib import resources


class PromptLoadError(RuntimeError):
    """Raised when a packaged prompt cannot be loaded."""


def load_prompt(name: str) -> str:
    prompt_name = name if name.endswith(".md") else f"{name}.md"
    try:
        return resources.files(__package__).joinpath(prompt_name).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PromptLoadError(f"prompt not found: {prompt_name}") from exc
