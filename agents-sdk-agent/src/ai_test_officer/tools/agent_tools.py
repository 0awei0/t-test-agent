from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..models import ChangedFile, CommandResult, GeneratedFile
from ..redaction import redact_secrets
from .local import LocalTestTools


@dataclass
class AgentRunTools:
    local: LocalTestTools
    changed_files: list[ChangedFile]
    context_dir: Path
    commands: list[CommandResult]
    generated_files: list[GeneratedFile]

    def list_changed_files(self) -> str:
        return json.dumps([item.__dict__ for item in self.changed_files], ensure_ascii=False, indent=2)

    def read_file_diff(self, path: str) -> str:
        diff_index = json.loads((self.context_dir / "diff-index.json").read_text(encoding="utf-8"))
        for item in diff_index:
            if item["path"] == path:
                artifact = (self.context_dir / item["artifact"]).resolve()
                _ensure_inside(self.context_dir, artifact)
                return redact_secrets(artifact.read_text(encoding="utf-8", errors="replace"))
        raise FileNotFoundError(f"diff not found for changed file: {path}")

    def read_file(self, path: str, start_line: int = 1, end_line: int = 200) -> str:
        return self.local.read_file_range(path, start_line, end_line)

    def search_repo(self, query: str) -> str:
        return self.local.search_repo(query)

    def get_package_scripts(self, package_json_path: str) -> str:
        data = json.loads(self.local.read_file(package_json_path))
        return json.dumps(data.get("scripts", {}), ensure_ascii=False, indent=2)

    def read_test_log(self, command_id: int) -> str:
        if command_id < 1 or command_id > len(self.commands):
            raise IndexError(f"command id out of range: {command_id}")
        path = self.commands[command_id - 1].log_path
        return redact_secrets(path.read_text(encoding="utf-8", errors="replace"))

    def write_temp_test(self, path: str, content: str, reason: str = "Agent generated temporary test.") -> GeneratedFile:
        generated = self.local.write_temp_file(path, content, reason)
        self.generated_files.append(generated)
        return generated

    def run_test_command(self, command: str) -> CommandResult:
        result = self.local.run_test_command(command)
        self.commands.append(result)
        return result


def _ensure_inside(root: Path, target: Path) -> None:
    resolved_root = root.resolve()
    if resolved_root not in target.parents and target != resolved_root:
        raise ValueError(f"path escapes context dir: {target}")
