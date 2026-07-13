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

    def memory(
        self,
        mode: str,
        source_chars: int,
        summary_chars: int,
        compression_ratio: float,
        artifact_count: int,
    ) -> None:
        self.emit(
            "memory",
            mode=mode,
            source_chars=source_chars,
            summary_chars=summary_chars,
            compression_ratio=compression_ratio,
            artifact_count=artifact_count,
        )

    def isolation(self) -> None:
        self.emit(
            "isolation",
            workspace="isolated-copy",
            source_repo="read-only",
            command_policy="test-command-whitelist",
            temp_write_scope="tests-and-evidence-only",
            remote_mutation="disabled",
        )

    def provenance(
        self,
        *,
        run_id: str,
        planner_mode: str,
        strict_tools_passed: bool,
        tool_calls: int,
        model_tool_calls: int,
        commands: int,
        generated_tests: int,
        evidence: int,
    ) -> None:
        self.emit(
            "provenance",
            run_id=run_id,
            planner_mode=planner_mode,
            strict_tools_passed=strict_tools_passed,
            tool_calls=tool_calls,
            model_tool_calls=model_tool_calls,
            commands=commands,
            generated_tests=generated_tests,
            evidence=evidence,
        )

    def safety_check(self, *, action: str, target: str, status: str, blocked_by: str, reason: str) -> None:
        self.emit(
            "safety_check",
            action=action,
            target=target,
            status=status,
            blocked_by=blocked_by,
            reason=reason,
        )

    def adaptation(self, *, kind: str, status: str, detail: str) -> None:
        self.emit("adaptation", kind=kind, status=status, detail=detail)

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
