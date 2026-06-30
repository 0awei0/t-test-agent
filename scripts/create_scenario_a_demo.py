#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from ai_test_officer.demo_scenarios import create_scenario_a_repo, default_demo_root


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a synthetic scenario A demo repo.")
    parser.add_argument(
        "--output",
        type=Path,
        default=default_demo_root(),
        help="Demo root directory. Scenario A is created under <output>/scenario-a.",
    )
    args = parser.parse_args()

    root = args.output.expanduser().resolve()
    repo = create_scenario_a_repo(root / "scenario-a")
    print(repo)
    print()
    print("Run:")
    print(
        "uv run ai-test-officer scenario run "
        "--scenario A "
        f"--demo-root {root} "
        "--dry-run"
    )


if __name__ == "__main__":
    main()
