from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .config import read_project_mcp_config


EXPECTED_MCP_SERVERS = ("tapd_mcp_http", "iWiki", "gongfeng", "playwright")


@dataclass(frozen=True)
class McpSmokeResult:
    config_path: Path | None
    servers: list[str]
    missing: list[str]
    passed: bool

    def to_json(self) -> str:
        return json.dumps(
            {
                "config_path": str(self.config_path) if self.config_path else None,
                "servers": self.servers,
                "missing": self.missing,
                "passed": self.passed,
            },
            ensure_ascii=False,
            indent=2,
        )


def run_mcp_config_smoke(repo_root: Path | str = ".") -> McpSmokeResult:
    config = read_project_mcp_config(repo_root)
    if config is None:
        return McpSmokeResult(config_path=None, servers=[], missing=list(EXPECTED_MCP_SERVERS), passed=False)
    servers = _server_names(config.text)
    missing = [server for server in EXPECTED_MCP_SERVERS if server not in servers]
    return McpSmokeResult(
        config_path=config.path,
        servers=servers,
        missing=missing,
        passed=not missing,
    )


def _server_names(text: str) -> list[str]:
    servers: list[str] = []
    for match in re.finditer(r"^\[mcp_servers\.([^\]]+)\]", text, flags=re.MULTILINE):
        servers.append(match.group(1))
    return servers
