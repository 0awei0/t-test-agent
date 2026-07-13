"""Structured event stream for the live AI Test Officer dashboard.

Each run appends newline-delimited JSON events to ``<run_dir>/events.jsonl``.
The live server tails this file and pushes events to browsers over SSE, so the
frontend can render the agent's execution in real time and replay a finished run.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path


class RunPhase:
    """High-level pipeline phases shown in the dashboard progress bar."""

    CHECKOUT = "checkout"
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    REPORTING = "reporting"
    ORDER = [CHECKOUT, PLANNING, EXECUTING, VALIDATING, REPORTING]


class EventSink:
    """Append-only JSONL writer for run events.

    Thread-safe: the agent loop and the SSE server may touch the same run from
    different threads. ``emit`` serializes a single JSON object per call.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = 0

    def emit(self, type: str, **data) -> None:
        with self._lock:
            self._seq += 1
            seq = self._seq
        event = {"seq": seq, "ts": time.time(), "type": type, "data": data}
        line = json.dumps(event, ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    # Convenience helpers used across the runner.
    def phase(self, phase: str, status: str, detail: str = "") -> None:
        self.emit("phase", phase=phase, status=status, detail=detail)

    def planner(self, step: str) -> None:
        self.emit("planner", step=step)

    def context(self, task: str, changed_files: list[dict[str, str]]) -> None:
        self.emit("context", task=task, changed_files=changed_files)

    def tool_call(
        self,
        id: str,
        tool: str,
        status: str,
        input: str | None = None,
        output: str | None = None,
        error: str | None = None,
        model_initiated: bool = True,
    ) -> None:
        self.emit(
            "tool_call",
            id=id,
            tool=tool,
            status=status,
            input=input,
            output=output,
            error=error,
            model_initiated=model_initiated,
        )

    def command(
        self,
        id: str,
        command: str,
        status: str,
        category: str | None = None,
        returncode: int | None = None,
        log_path: str | None = None,
    ) -> None:
        self.emit(
            "command",
            id=id,
            command=command,
            status=status,
            category=category,
            returncode=returncode,
            log_path=log_path,
        )

    def evidence(self, path: str, kind: str, caption: str = "") -> None:
        self.emit("evidence", path=path, kind=kind, caption=caption)

    def verdict(
        self,
        verdict: str,
        risk: str,
        failure_category: str = "",
        summary: str = "",
    ) -> None:
        self.emit(
            "verdict",
            verdict=verdict,
            risk=risk,
            failure_category=failure_category,
            summary=summary,
        )

    def done(self) -> None:
        self.emit("done")
