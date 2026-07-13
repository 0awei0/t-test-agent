from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReplaySpec:
    task_id: str
    scenario: str


REPLAY_SPECS = (
    ReplaySpec("task-42", "promotion-chain"),
    ReplaySpec("task-43", "promotion-chain-pass"),
    ReplaySpec("task-45", "release-guard"),
    ReplaySpec("task-46", "release-guard-pass"),
    ReplaySpec("task-47", "refund-guard"),
    ReplaySpec("task-48", "refund-guard-pass"),
    ReplaySpec("task-53", "agent-loop"),
    ReplaySpec("task-55", "fullstack"),
)

DEFAULT_REPLAY_TASK_ID = "task-45"
