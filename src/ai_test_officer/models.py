from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TestTask:
    """User request and local inputs for one AI Test Officer run."""

    task: str
    repo_path: Path
    diff_path: Path | None = None
    requirement_path: Path | None = None
    output_path: Path = Path("reports/latest-report.md")
    allow_edits: bool = False

    def resolved_repo(self) -> Path:
        return self.repo_path.expanduser().resolve()

    def resolved_output(self) -> Path:
        output = self.output_path.expanduser()
        if output.is_absolute():
            return output
        return self.resolved_repo() / output

