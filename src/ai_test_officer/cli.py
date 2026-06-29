from __future__ import annotations

import argparse
from pathlib import Path

from .codex_runner import CodexDependencyError, CodexRunner
from .models import TestTask
from .prompts import build_test_officer_prompt
from .report import dry_run_report, write_report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ai-test-officer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_common_args(subparsers.add_parser("prompt", help="Print the Codex prompt."))
    run_parser = subparsers.add_parser("run", help="Run the AI Test Officer workflow.")
    _add_common_args(run_parser)
    run_parser.add_argument("--dry-run", action="store_true", help="Do not call Codex SDK.")
    run_parser.add_argument(
        "--model",
        default=None,
        help="Codex model override. Defaults to AI_TEST_OFFICER_MODEL or gpt-5.4.",
    )
    run_parser.add_argument(
        "--sandbox",
        choices=["read_only", "workspace_write", "full_access"],
        default="workspace_write",
        help="Codex SDK sandbox preset.",
    )

    args = parser.parse_args(argv)
    task = _task_from_args(args)
    prompt = build_test_officer_prompt(task)

    if args.command == "prompt":
        print(prompt)
        return

    if args.dry_run:
        body = dry_run_report(prompt)
        path = write_report(task, body, dry_run=True)
        print(f"Wrote dry-run report: {path}")
        return

    try:
        body = CodexRunner(model=args.model, sandbox=args.sandbox).run(prompt, task.resolved_repo())
    except CodexDependencyError as exc:
        raise SystemExit(str(exc)) from exc

    path = write_report(task, body, dry_run=False)
    print(f"Wrote Codex report: {path}")


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task", required=True, help="Testing request for the AI Test Officer.")
    parser.add_argument("--repo", default=".", help="Repository path to inspect.")
    parser.add_argument("--diff", dest="diff_path", default=None, help="Optional PR diff text file.")
    parser.add_argument(
        "--requirement",
        dest="requirement_path",
        default=None,
        help="Optional requirement or PRD text file.",
    )
    parser.add_argument(
        "--output",
        default="reports/latest-report.md",
        help="Markdown report output path.",
    )
    parser.add_argument(
        "--allow-edits",
        action="store_true",
        help="Allow Codex to edit files when creating or improving tests.",
    )


def _task_from_args(args: argparse.Namespace) -> TestTask:
    return TestTask(
        task=args.task,
        repo_path=Path(args.repo),
        diff_path=Path(args.diff_path) if args.diff_path else None,
        requirement_path=Path(args.requirement_path) if args.requirement_path else None,
        output_path=Path(args.output),
        allow_edits=args.allow_edits,
    )

