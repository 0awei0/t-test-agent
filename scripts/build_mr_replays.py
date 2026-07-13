from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from ai_test_officer.agent import load_env_file
from ai_test_officer.demo import DemoRunConfig, run_agent_loop_demo, run_fullstack_demo, run_investigation_demo, run_release_guard_demo
from ai_test_officer.demo.replay_catalog import DEFAULT_REPLAY_TASK_ID, REPLAY_SPECS
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
            if spec.scenario == "agent-loop":
                record = run_agent_loop_demo(config)
            elif spec.scenario == "fullstack":
                record = run_fullstack_demo(config)
            elif spec.scenario in {"release-guard", "release-guard-pass"}:
                record = run_release_guard_demo(config, repaired=spec.scenario.endswith("-pass"))
            else:
                record = run_investigation_demo(config, spec.scenario)
            run_dir = record.run_dir
            print(f"{spec.task_id}: {record.verdict}/{record.risk} tools={len(record.agent_turns)}")
        replay_runs[spec.task_id] = (spec.scenario, run_dir)

    if args.task_id:
        replay_runs = {
            spec.task_id: (spec.scenario, runs_root / spec.task_id)
            for spec in REPLAY_SPECS
            if (runs_root / spec.task_id / "events.jsonl").exists()
        }
    catalog = write_local_replay_catalog(runs_root, replay_runs, default_task_id=DEFAULT_REPLAY_TASK_ID)
    print(f"Local replay catalog: {catalog}")
    if args.dashboard_dir:
        manifest = export_replay_catalog(
            replay_runs,
            Path(args.dashboard_dir),
            default_task_id=DEFAULT_REPLAY_TASK_ID,
        )
        print(f"Static replay manifest: {manifest}")


if __name__ == "__main__":
    main()
