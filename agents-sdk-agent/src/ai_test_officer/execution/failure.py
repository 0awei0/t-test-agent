from __future__ import annotations

from ..models import CommandResult, RunRecord

BUSINESS_FAILURE = "business-failure"
TEST_FAILURE = "test-failure"
DEPENDENCY_MISSING = "dependency-missing"
ENVIRONMENT_MISSING = "environment-missing"
NO_TEST_SELECTED = "no-test-selected"
PASSED = "passed"


def classify_record_failures(record: RunRecord) -> RunRecord:
    failures = [command for command in record.commands if command.returncode != 0]
    if not record.commands:
        record.failure_category = NO_TEST_SELECTED
        record.blocked_reason = "No safe targeted test command was selected."
        return record
    if not failures:
        record.failure_category = PASSED
        record.blocked_reason = ""
        return record

    categories = [_classify_command_failure(command) for command in failures]
    if all(category == DEPENDENCY_MISSING for category, _ in categories):
        record.failure_category = DEPENDENCY_MISSING
        record.verdict = "blocked"
        record.risk = "high"
    elif any(category == ENVIRONMENT_MISSING for category, _ in categories):
        record.failure_category = ENVIRONMENT_MISSING
        record.verdict = "blocked"
        record.risk = "high"
    elif any(category == TEST_FAILURE for category, _ in categories):
        record.failure_category = TEST_FAILURE
    else:
        record.failure_category = BUSINESS_FAILURE
    record.blocked_reason = "; ".join(reason for _, reason in categories if reason)
    if record.verdict == "blocked":
        record.summary = (
            f"{len(failures)} test command(s) were blocked by {record.failure_category}; "
            "this does not prove a business logic regression."
        )
    return record


def classify_command_failure(command: CommandResult) -> tuple[str, str]:
    return _classify_command_failure(command)


def _classify_command_failure(command: CommandResult) -> tuple[str, str]:
    output = f"{command.stderr}\n{command.stdout}".lower()
    if command.returncode == 124 or "timed out" in output or "(timeout)" in output:
        return ENVIRONMENT_MISSING, _first_relevant_line(command)
    if "fail:" in output or "assertionerror" in output:
        return TEST_FAILURE, _first_relevant_line(command)
    if "failed" in output and "assert" in output:
        return TEST_FAILURE, _first_relevant_line(command)
    if "command not found" in output or "cannot find module" in output:
        return DEPENDENCY_MISSING, _first_relevant_line(command)
    if "module_not_found" in output or "no module named" in output:
        return DEPENDENCY_MISSING, _first_relevant_line(command)
    if "missing script" in output:
        return DEPENDENCY_MISSING, _first_relevant_line(command)
    if "browser" in output and ("not found" in output or "install" in output):
        return ENVIRONMENT_MISSING, _first_relevant_line(command)
    if "playwright" in output and ("install" in output or "missing" in output):
        return ENVIRONMENT_MISSING, _first_relevant_line(command)
    if "assert" in output or "failed" in output or "error:" in output:
        return TEST_FAILURE, _first_relevant_line(command)
    return BUSINESS_FAILURE, _first_relevant_line(command)


def _first_relevant_line(command: CommandResult) -> str:
    text = f"{command.stderr}\n{command.stdout}"
    for raw in text.splitlines():
        line = raw.strip()
        if line:
            return line[:240]
    return f"{command.command} exited {command.returncode}"
