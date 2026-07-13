from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReplaySpec:
    task_id: str
    tapd_id: str
    mr_iid: str
    scenario: str
    expected_verdict: str
    expected_risk: str


REPLAY_SPECS = (
    ReplaySpec("task-42", "TAPD-114514", "!42", "promotion-chain", "fail", "high"),
    ReplaySpec("task-43", "TAPD-114515", "!43", "promotion-chain-pass", "pass", "low"),
    ReplaySpec("task-45", "TAPD-114516", "!45", "release-guard", "fail", "high"),
    ReplaySpec("task-46", "TAPD-114517", "!46", "release-guard-pass", "pass", "low"),
    ReplaySpec("task-47", "TAPD-114518", "!47", "refund-guard", "fail", "high"),
    ReplaySpec("task-48", "TAPD-114519", "!48", "refund-guard-pass", "pass", "low"),
    ReplaySpec("task-53", "TAPD-114520", "!53", "agent-loop", "fail", "high"),
    ReplaySpec("task-55", "TAPD-114521", "!55", "fullstack", "fail", "high"),
)

DEFAULT_REPLAY_TASK_ID = "task-45"


def replay_manifest_metadata() -> dict[str, dict[str, str]]:
    return {
        spec.task_id: {
            "tapd_id": spec.tapd_id,
            "mr_iid": spec.mr_iid,
            "expected_verdict": spec.expected_verdict,
            "expected_risk": spec.expected_risk,
        }
        for spec in REPLAY_SPECS
    }
