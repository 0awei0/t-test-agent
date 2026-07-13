from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptBudget:
    max_chars: int
