from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class McpConfig:
    path: Path
    text: str


def project_mcp_config_path(repo_root: Path | str = ".") -> Path:
    return Path(repo_root).expanduser().resolve() / ".codex" / "config.toml"


def read_project_mcp_config(repo_root: Path | str = ".") -> McpConfig | None:
    path = project_mcp_config_path(repo_root)
    if not path.exists():
        return None
    return McpConfig(path=path, text=path.read_text(encoding="utf-8"))
