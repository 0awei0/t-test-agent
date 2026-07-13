from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from ai_test_officer.agent import load_env_file
from ai_test_officer.demo import DemoRunConfig, run_agent_loop_demo, run_fullstack_demo, run_investigation_demo, run_release_guard_demo
from ai_test_officer.demo.replay_catalog import DEFAULT_REPLAY_TASK_ID, REPLAY_SPECS, replay_manifest_metadata
from ai_test_officer.models import RunRecord
from ai_test_officer.report_site import export_replay_catalog, write_local_replay_catalog


def main() -> None:
    parser = argparse.ArgumentParser(description="Run and package all TAPD/MR competition replays.")
    parser.add_argument("--runs-root", default="runs/mr-replays")
    parser.add_argument("--demo-root", default="runs/mr-replay-demos")
    parser.add_argument("--dashboard-dir", default=None)
    parser.add_argument("--env", default=".env")
    parser.add_argument("--reuse-existing", action="store_true")
    parser.add_argument("--task-id", action="append", default=[], help="Only run/package selected task id(s).")
    parser.add_argument("--max-agent-turns", type=int, default=30)
    parser.add_argument("--max-attempts", type=int, default=3, help="Retry an unstable Agent run until its contract passes.")
    args = parser.parse_args()

    load_env_file(Path(args.env))
    runs_root = Path(args.runs_root)
    replay_runs: dict[str, tuple[str, Path]] = {}
    selected_specs = [spec for spec in REPLAY_SPECS if not args.task_id or spec.task_id in args.task_id]
    if args.task_id and len(selected_specs) != len(set(args.task_id)):
        raise SystemExit("unknown --task-id value")
    for spec in selected_specs:
        run_dir = runs_root / spec.task_id
        if not args.reuse_existing or not (run_dir / "events.jsonl").exists():
            for attempt in range(1, args.max_attempts + 1):
                if run_dir.exists():
                    shutil.rmtree(run_dir)
                config = DemoRunConfig(
                    demo_root=Path(args.demo_root),
                    planner_mode="agent-strict",
                    allow_temp_test_code=True,
                    runs_root=runs_root,
                    run_id=spec.task_id,
                    memory_mode="structured",
                    max_agent_turns=args.max_agent_turns,
                )
                record = _run_spec(spec.scenario, config)
                run_dir = record.run_dir
                passed = (
                    record.verdict == spec.expected_verdict
                    and record.risk == spec.expected_risk
                    and record.required_tool_check.passed
                )
                print(
                    f"{spec.task_id}: attempt={attempt}/{args.max_attempts} "
                    f"{record.verdict}/{record.risk} tools={len(record.agent_turns)} "
                    f"strict={record.required_tool_check.passed}"
                )
                if passed:
                    break
                if attempt == args.max_attempts:
                    raise SystemExit(
                        f"{spec.task_id} failed replay contract after {args.max_attempts} attempts; "
                        f"expected {spec.expected_verdict}/{spec.expected_risk} with strict tools"
                    )
                print(f"RETRY {spec.task_id}: Agent ended before satisfying the competition contract")
        else:
            _validate_reused_run(spec.task_id, run_dir, spec.expected_verdict, spec.expected_risk)
        replay_runs[spec.task_id] = (spec.scenario, run_dir)

    if args.task_id:
        replay_runs = {
            spec.task_id: (spec.scenario, runs_root / spec.task_id)
            for spec in REPLAY_SPECS
            if (runs_root / spec.task_id / "events.jsonl").exists()
        }
    metadata = replay_manifest_metadata()
    catalog = write_local_replay_catalog(
        runs_root,
        replay_runs,
        default_task_id=DEFAULT_REPLAY_TASK_ID,
        item_metadata=metadata,
    )
    print(f"Local replay catalog: {catalog}")
    if args.dashboard_dir:
        manifest = export_replay_catalog(
            replay_runs,
            Path(args.dashboard_dir),
            default_task_id=DEFAULT_REPLAY_TASK_ID,
            item_metadata=metadata,
        )
        print(f"Static replay manifest: {manifest}")


def _run_spec(scenario: str, config: DemoRunConfig) -> RunRecord:
    if scenario == "agent-loop":
        return run_agent_loop_demo(config)
    if scenario == "fullstack":
        return run_fullstack_demo(config)
    if scenario in {"release-guard", "release-guard-pass"}:
        return run_release_guard_demo(config, repaired=scenario.endswith("-pass"))
    return run_investigation_demo(config, scenario)


def _validate_reused_run(task_id: str, run_dir: Path, expected_verdict: str, expected_risk: str) -> None:
    data = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    tool_check = data.get("required_tool_check") if isinstance(data.get("required_tool_check"), dict) else {}
    if data.get("verdict") != expected_verdict or data.get("risk") != expected_risk or tool_check.get("passed") is not True:
        raise SystemExit(f"{task_id} reused replay does not satisfy its competition contract")


if __name__ == "__main__":
    main()
