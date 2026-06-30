#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from ai_test_officer.demo_scenarios import default_demo_root, ensure_all_scenario_demos


def main() -> None:
    parser = argparse.ArgumentParser(description="Create synthetic AI Test Officer scenario demos.")
    parser.add_argument(
        "--output",
        type=Path,
        default=default_demo_root(),
        help="Demo root directory.",
    )
    args = parser.parse_args()

    demos = ensure_all_scenario_demos(args.output)
    print(args.output.expanduser().resolve())
    print()
    for key, demo in demos.items():
        print(f"Scenario {key}: {demo.repo_path}")
        if demo.requirement_path:
            print(f"  Requirement: {demo.requirement_path}")
    print()
    print("Run:")
    for key in ("A", "B", "C"):
        print(
            "uv run ai-test-officer scenario run "
            f"--scenario {key} "
            f"--demo-root {args.output.expanduser().resolve()} "
            "--dry-run"
        )


if __name__ == "__main__":
    main()
