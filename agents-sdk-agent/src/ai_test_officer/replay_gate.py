from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .demo.replay_catalog import DEFAULT_REPLAY_TASK_ID, REPLAY_SPECS, ReplaySpec
from .release_gate import ReleaseGateError, validate_run_file
from .showcase_doctor import _content_violation


COMPLEX_EVENT_TYPES = {
    "context",
    "isolation",
    "planner",
    "test_plan",
    "plan_update",
    "tool_call",
    "command",
    "evidence",
    "memory",
    "verdict",
    "done",
}

REQUIRED_REPLAY_EVENT_TYPES = {
    "isolation",
    "test_plan",
    "plan_update",
    "tool_call",
    "verdict",
    "done",
}


def validate_replay_package(manifest_path: Path, runs_root: Path, public_root: Path) -> None:
    manifest = _read_json_object(manifest_path, "replay manifest")
    items = manifest.get("items")
    _expect(isinstance(items, list), "manifest items must be a list")
    assert isinstance(items, list)
    specs = _validated_specs()
    expected_ids = set(specs)
    actual_ids = [str(item.get("task_id")) for item in items if isinstance(item, dict)]
    _expect(len(items) == len(specs), "unexpected replay count", len(items))
    _expect(len(actual_ids) == len(set(actual_ids)), "duplicate task_id in replay manifest")
    _expect(set(actual_ids) == expected_ids, "replay task ids do not match competition catalog", actual_ids)
    _expect(manifest.get("default_task_id") == DEFAULT_REPLAY_TASK_ID, "unexpected default replay task")

    by_id = {str(item["task_id"]): item for item in items if isinstance(item, dict) and "task_id" in item}
    for task_id, spec in specs.items():
        item = by_id[task_id]
        _validate_manifest_item(item, spec)
        run_dir = runs_root / task_id
        validate_run_file(
            run_dir / "run.json",
            expected_verdict=spec.expected_verdict,
            expected_risk=spec.expected_risk,
            require_agent_tools=True,
        )
        required_events = COMPLEX_EVENT_TYPES if task_id == DEFAULT_REPLAY_TASK_ID else REQUIRED_REPLAY_EVENT_TYPES
        _validate_events(run_dir / "events.jsonl", required_events)
        public_events = _validate_public_replay(public_root / "replays" / task_id)
        _expect("provenance" in public_events, f"{task_id} public replay is missing provenance")
        _expect("test_plan" in public_events, f"{task_id} public replay is missing test plan")
        _expect("plan_update" in public_events, f"{task_id} public replay is missing test plan progress")
        if task_id == DEFAULT_REPLAY_TASK_ID:
            _expect("adaptation" in public_events, f"{task_id} public replay is missing failure-driven adaptation")
        if task_id == "task-53":
            _expect("safety_check" in public_events, "task-53 public replay is missing an actual safety block")


def _validated_specs() -> dict[str, ReplaySpec]:
    specs = {spec.task_id: spec for spec in REPLAY_SPECS}
    _expect(len(specs) == len(REPLAY_SPECS), "duplicate task_id in replay specs")
    _expect(len({spec.tapd_id for spec in REPLAY_SPECS}) == len(REPLAY_SPECS), "duplicate TAPD id in replay specs")
    _expect(len({spec.mr_iid for spec in REPLAY_SPECS}) == len(REPLAY_SPECS), "duplicate MR iid in replay specs")
    return specs


def _validate_manifest_item(item: dict[str, Any], spec: ReplaySpec) -> None:
    expected = {
        "scenario": spec.scenario,
        "tapd_id": spec.tapd_id,
        "mr_iid": spec.mr_iid,
        "expected_verdict": spec.expected_verdict,
        "expected_risk": spec.expected_risk,
        "verdict": spec.expected_verdict,
        "risk": spec.expected_risk,
    }
    for key, value in expected.items():
        _expect(item.get(key) == value, f"{spec.task_id} has unexpected {key}", item.get(key))
    _expect(int(item.get("tool_calls") or 0) > 0, f"{spec.task_id} has no public tool calls")
    _expect(int(item.get("planner_steps") or 0) > 0, f"{spec.task_id} has no planner events")


def _validate_events(path: Path, required_types: set[str]) -> None:
    if not path.is_file():
        raise ReleaseGateError(f"events file not found: {path}")
    event_types: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReleaseGateError(f"invalid event JSON at {path}:{line_number}: {exc}") from exc
        _expect(isinstance(event, dict), f"event must be an object at {path}:{line_number}")
        event_types.add(str(event.get("type") or ""))
    missing = sorted(required_types - event_types)
    _expect(not missing, f"required replay events are missing from {path.name}", missing)


def _validate_public_replay(replay_dir: Path) -> set[str]:
    _expect(replay_dir.is_dir(), "public replay directory is missing", replay_dir)
    for name in ("events.jsonl", "report.html"):
        _expect((replay_dir / name).is_file(), f"public replay file is missing: {name}")
    _expect(not (replay_dir / "run.json").exists(), "full run.json leaked into public replay")
    for path in replay_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".html", ".md", ".json", ".jsonl", ".txt", ".js", ".css"}:
            continue
        violation = _content_violation(path.read_text(encoding="utf-8", errors="replace"))
        _expect(not violation, f"public replay contains forbidden content in {path.name}", violation)
    event_types: set[str] = set()
    for line in (replay_dir / "events.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if isinstance(event, dict):
            event_types.add(str(event.get("type") or ""))
    return event_types


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReleaseGateError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReleaseGateError(f"invalid {label}: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ReleaseGateError(f"{label} root must be an object: {path}")
    return data


def _expect(condition: bool, message: str, value: object | None = None) -> None:
    if condition:
        return
    suffix = f": {value!r}" if value is not None else ""
    raise ReleaseGateError(message + suffix)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Validate the complete competition replay package.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--public-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        validate_replay_package(args.manifest, args.runs_root, args.public_root)
    except ReleaseGateError as exc:
        raise SystemExit(f"competition replay gate failed: {exc}") from exc
    print(f"PASS all {len(REPLAY_SPECS)} competition replay contracts")


if __name__ == "__main__":
    main()
