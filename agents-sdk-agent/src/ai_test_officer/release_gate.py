from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class ReleaseGateError(ValueError):
    """Raised when a competition run does not satisfy the release contract."""


def validate_run_record(
    data: dict[str, Any],
    *,
    expected_verdict: str,
    expected_risk: str,
    require_agent_tools: bool = False,
) -> None:
    _expect(data.get("verdict") == expected_verdict, "unexpected verdict", data.get("verdict"))
    _expect(data.get("risk") == expected_risk, "unexpected risk", data.get("risk"))
    _expect(bool(data.get("commands")), "run did not execute any test commands")
    _expect(bool(data.get("summary")), "run summary is empty")

    if not require_agent_tools:
        return

    _expect(data.get("planner_mode") == "agent-strict", "planner did not use agent-strict")
    tool_check = data.get("required_tool_check")
    _expect(isinstance(tool_check, dict), "required tool check is missing")
    assert isinstance(tool_check, dict)
    _expect(tool_check.get("passed") is True, "required Agent tool check failed")
    _expect(not tool_check.get("missing"), "required Agent tools are missing", tool_check.get("missing"))
    _expect(bool(data.get("agent_turns")), "Agent did not record tool turns")
    _expect(bool(str(data.get("agent_final_output") or "").strip()), "Agent final output is empty")


def validate_run_file(
    path: Path,
    *,
    expected_verdict: str,
    expected_risk: str,
    require_agent_tools: bool = False,
) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReleaseGateError(f"run file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReleaseGateError(f"invalid run JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ReleaseGateError(f"run JSON root must be an object: {path}")
    validate_run_record(
        data,
        expected_verdict=expected_verdict,
        expected_risk=expected_risk,
        require_agent_tools=require_agent_tools,
    )


def _expect(condition: bool, message: str, value: object | None = None) -> None:
    if condition:
        return
    suffix = f": {value!r}" if value is not None else ""
    raise ReleaseGateError(message + suffix)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Validate one AI Test Officer competition run.")
    parser.add_argument("run_json", type=Path)
    parser.add_argument("--expect-verdict", required=True)
    parser.add_argument("--expect-risk", required=True)
    parser.add_argument("--require-agent-tools", action="store_true")
    args = parser.parse_args(argv)
    try:
        validate_run_file(
            args.run_json,
            expected_verdict=args.expect_verdict,
            expected_risk=args.expect_risk,
            require_agent_tools=args.require_agent_tools,
        )
    except ReleaseGateError as exc:
        raise SystemExit(f"competition release gate failed: {exc}") from exc
    print(f"PASS run contract: {args.run_json}")


if __name__ == "__main__":
    main()
