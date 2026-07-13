from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillInstructions:
    path: Path
    text: str


def repo_skill_path(repo_root: Path | str = ".") -> Path:
    return Path(repo_root).expanduser().resolve() / ".agents" / "skills" / "ai-test-officer" / "SKILL.md"


def read_repo_skill(repo_root: Path | str = ".", max_chars: int = 20_000) -> SkillInstructions | None:
    path = repo_skill_path(repo_root)
    if not path.exists():
        return None
    return SkillInstructions(path=path, text=path.read_text(encoding="utf-8")[:max_chars])
