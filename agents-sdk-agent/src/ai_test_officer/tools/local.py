from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ..config import COMMAND_TIMEOUT_SEC, MAX_TOOL_OUTPUT_CHARS
from ..models import CommandResult, GeneratedFile
from ..redaction import redact_secrets
from .safety import validate_temp_write_path, validate_test_command


@dataclass
class LocalTestTools:
    repo_path: Path
    logs_dir: Path
    allow_temp_test_code: bool
    _command_index: int = 0

    def read_file(self, relative_path: str, max_chars: int = MAX_TOOL_OUTPUT_CHARS) -> str:
        target = (self.repo_path / relative_path).resolve()
        self._ensure_inside_repo(target)
        text = target.read_text(encoding="utf-8", errors="replace")
        return text[:max_chars]

    def read_file_range(self, relative_path: str, start_line: int, end_line: int) -> str:
        target = (self.repo_path / relative_path).resolve()
        self._ensure_inside_repo(target)
        if start_line < 1 or end_line < start_line:
            raise ValueError("line range must be 1-based and increasing")
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        selected = lines[start_line - 1 : end_line]
        return "\n".join(selected)[:MAX_TOOL_OUTPUT_CHARS]

    def search_repo(self, query: str, max_results: int = 50) -> str:
        proc = subprocess.run(
            ["rg", "-n", "--", query],
            cwd=self.repo_path,
            text=True,
            capture_output=True,
            timeout=COMMAND_TIMEOUT_SEC,
            check=False,
        )
        output = proc.stdout if proc.returncode in {0, 1} else proc.stderr
        return redact_secrets(_truncate(output))

    def write_temp_file(self, relative_path: str, content: str, reason: str) -> GeneratedFile:
        target = validate_temp_write_path(self.repo_path, relative_path, self.allow_temp_test_code)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return GeneratedFile(path=target, reason=reason)

    def run_test_command(self, command: str, timeout_sec: int = COMMAND_TIMEOUT_SEC) -> CommandResult:
        argv = validate_test_command(command)
        execution_argv = _runtime_argv(argv)
        self._command_index += 1
        log_path = self.logs_dir / f"command-{self._command_index:02d}.log"
        timed_out = False
        try:
            proc = subprocess.run(
                execution_argv,
                cwd=self.repo_path,
                text=True,
                capture_output=True,
                timeout=timeout_sec,
                check=False,
            )
            returncode = proc.returncode
            raw_stdout = proc.stdout
            raw_stderr = proc.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            returncode = 124
            raw_stdout = _coerce_timeout_output(exc.stdout)
            raw_stderr = _coerce_timeout_output(exc.stderr)
            raw_stderr = f"{raw_stderr}\ncommand timed out after {timeout_sec}s".strip()
        stdout = redact_secrets(_truncate(raw_stdout))
        stderr = redact_secrets(_truncate(raw_stderr))
        log_path.write_text(
            f"$ {command}\n\n# stdout\n{stdout}\n\n# stderr\n{stderr}\n",
            encoding="utf-8",
        )
        if timed_out:
            stderr = f"{stderr}\n(timeout)"
        return CommandResult(command, returncode, stdout, stderr, log_path)

    def _ensure_inside_repo(self, path: Path) -> None:
        repo = self.repo_path.resolve()
        if repo not in path.parents and path != repo:
            raise ValueError(f"path escapes workspace repo: {path}")


def _truncate(text: str) -> str:
    if len(text) <= MAX_TOOL_OUTPUT_CHARS:
        return text
    return text[:MAX_TOOL_OUTPUT_CHARS] + "\n...[truncated]\n"


def _coerce_timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _runtime_argv(argv: list[str]) -> list[str]:
    if argv and argv[0] in {"python", "python3"}:
        return [sys.executable, *argv[1:]]
    return argv
