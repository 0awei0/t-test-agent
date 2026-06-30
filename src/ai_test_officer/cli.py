from __future__ import annotations

import argparse
from pathlib import Path

from .codex_runner import CodexDependencyError, CodexRunner
from .demo_scenarios import default_demo_root
from .doctor import exit_code, load_env, render_summary, run_checks
from .git_diff import GitDiffError, collect_git_range_diff, collect_last_commit_diff
from .models import TestTask
from .prompts import build_test_officer_prompt
from .report import dry_run_report, run_json_path_for, write_report
from .scenario_runner import (
    ScenarioRunConfig,
    create_scenario_demos,
    render_created_demos,
    render_scenario_result,
    run_scenario,
)
from .wecom_bot import (
    build_notification_content,
    build_wecom_payload,
    render_dry_run,
    resolve_wecom_webhook,
    send_wecom_payload,
)
from .visualizer import visualize_report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ai-test-officer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_common_args(subparsers.add_parser("prompt", help="Print the Codex prompt."))
    scenario_parser = subparsers.add_parser("scenario", help="Create and run synthetic A/B/C demos.")
    _add_scenario_args(scenario_parser)
    doctor_parser = subparsers.add_parser("doctor", help="Check internal integrations.")
    doctor_parser.add_argument("--env", default=".env", help="Path to local dotenv file.")
    doctor_parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Timeout in seconds for each network or command probe.",
    )
    notify_parser = subparsers.add_parser("notify", help="Send or simulate a WeCom bot message.")
    notify_parser.add_argument("--env", default=".env", help="Path to local dotenv file.")
    notify_parser.add_argument("--message", default=None, help="Notification body.")
    notify_parser.add_argument("--report", default=None, help="Markdown report to include as preview.")
    notify_parser.add_argument(
        "--title",
        default="AI Test Officer",
        help="Notification title.",
    )
    notify_parser.add_argument(
        "--msgtype",
        choices=["markdown", "text"],
        default="markdown",
        help="WeCom message type.",
    )
    notify_parser.add_argument("--dry-run", action="store_true", help="Print payload without sending.")
    notify_parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Timeout in seconds for the WeCom webhook request.",
    )
    visualize_parser = subparsers.add_parser("visualize", help="Render a static HTML report.")
    visualize_parser.add_argument("--report", required=True, help="Markdown report path.")
    visualize_parser.add_argument(
        "--run-json",
        default=None,
        help="Run metadata JSON. Defaults to the report sidecar JSON.",
    )
    visualize_parser.add_argument("--output", default=None, help="HTML output path.")
    run_parser = subparsers.add_parser("run", help="Run the AI Test Officer workflow.")
    _add_common_args(run_parser)
    run_parser.add_argument("--dry-run", action="store_true", help="Do not call Codex SDK.")
    run_parser.add_argument("--visualize", action="store_true", help="Generate a static HTML report.")
    run_parser.add_argument("--html-output", default=None, help="Static HTML report output path.")
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
    run_parser.add_argument(
        "--save-thread",
        action="store_true",
        help="Keep the Codex SDK thread visible in the Codex sidebar for debugging.",
    )

    args = parser.parse_args(argv)

    if args.command == "doctor":
        results = run_checks(Path(args.env), timeout=args.timeout)
        print(render_summary(results))
        raise SystemExit(exit_code(results))

    if args.command == "scenario":
        _scenario_from_args(args)
        return

    if args.command == "notify":
        _notify_from_args(args)
        return

    if args.command == "visualize":
        _visualize_from_args(args)
        return

    try:
        task = _task_from_args(args)
    except GitDiffError as exc:
        raise SystemExit(f"Git diff input error: {exc}") from exc
    prompt = build_test_officer_prompt(task)

    if args.command == "prompt":
        print(prompt)
        return

    if args.dry_run:
        body = dry_run_report(prompt)
        path = write_report(task, body, dry_run=True)
        print(f"Wrote dry-run report: {path}")
        if args.visualize:
            print(f"Wrote HTML report: {_visualize_report(path, args.html_output)}")
        return

    try:
        body = CodexRunner(
            model=args.model,
            sandbox=args.sandbox,
            ephemeral=not args.save_thread,
            auto_archive=not args.save_thread,
        ).run(prompt, task.resolved_repo())
    except CodexDependencyError as exc:
        raise SystemExit(str(exc)) from exc

    path = write_report(task, body, dry_run=False)
    print(f"Wrote Codex report: {path}")
    if args.visualize:
        print(f"Wrote HTML report: {_visualize_report(path, args.html_output)}")


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task", required=True, help="Testing request for the AI Test Officer.")
    parser.add_argument("--repo", default=".", help="Repository path to inspect.")
    diff_group = parser.add_mutually_exclusive_group()
    diff_group.add_argument(
        "--diff",
        dest="diff_path",
        default=None,
        help="Optional PR diff text file.",
    )
    diff_group.add_argument(
        "--last-commit",
        action="store_true",
        help="Use local git diff for HEAD~1..HEAD.",
    )
    diff_group.add_argument(
        "--git-range",
        dest="git_range",
        default=None,
        help="Use local git diff for <base>..<head>.",
    )
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


def _add_scenario_args(parser: argparse.ArgumentParser) -> None:
    subparsers = parser.add_subparsers(dest="scenario_command", required=True)

    create = subparsers.add_parser("create", help="Create synthetic A/B/C demo repositories.")
    create.add_argument(
        "--scenario",
        choices=["A", "A-fullstack", "B", "C", "all"],
        default="all",
        help="Scenario demo to create.",
    )
    create.add_argument("--demo-root", default=None, help="Synthetic scenario demo root.")

    run = subparsers.add_parser("run", help="Run one synthetic scenario workflow.")
    run.add_argument(
        "--scenario",
        choices=["A", "A-fullstack", "B", "C"],
        required=True,
        help="Scenario workflow to run.",
    )
    run.add_argument("--demo-root", default=None, help="Synthetic scenario demo root.")
    run.add_argument("--env", default=".env", help="Path to local dotenv file for --send.")
    run.add_argument("--dry-run", action="store_true", help="Do not call Codex SDK.")
    run.add_argument("--send", action="store_true", help="Send the report summary to WeCom.")
    run.add_argument("--visualize", action="store_true", help="Generate a static HTML report.")
    run.add_argument("--html-output", default=None, help="Static HTML report output path.")
    run.add_argument("--model", default=None, help="Codex model override.")
    run.add_argument(
        "--sandbox",
        choices=["read_only", "workspace_write", "full_access"],
        default="workspace_write",
        help="Codex SDK sandbox preset.",
    )
    run.add_argument(
        "--save-thread",
        action="store_true",
        help="Keep the Codex SDK scenario thread visible in the Codex sidebar for debugging.",
    )
    run.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Timeout in seconds for the optional WeCom webhook request.",
    )


def _task_from_args(args: argparse.Namespace) -> TestTask:
    repo_path = Path(args.repo)
    local_diff = None
    if getattr(args, "last_commit", False):
        local_diff = collect_last_commit_diff(repo_path)
    elif getattr(args, "git_range", None):
        local_diff = collect_git_range_diff(repo_path, args.git_range)

    return TestTask(
        task=args.task,
        repo_path=repo_path,
        diff_path=Path(args.diff_path) if args.diff_path else None,
        diff_text=local_diff.diff if local_diff else None,
        diff_label=local_diff.label if local_diff else None,
        changed_files=local_diff.name_status if local_diff else None,
        requirement_path=Path(args.requirement_path) if args.requirement_path else None,
        output_path=Path(args.output),
        allow_edits=args.allow_edits,
    )


def _scenario_from_args(args: argparse.Namespace) -> None:
    demo_root = _demo_root_from_args(args.demo_root)
    if args.scenario_command == "create":
        demos = create_scenario_demos(demo_root, args.scenario)
        print(demo_root.expanduser().resolve())
        print()
        print(render_created_demos(demos))
        return

    if args.dry_run and args.send:
        raise SystemExit("Dry-run reports are local diagnostics; run without --dry-run to send a test report.")

    try:
        result = run_scenario(
            args.scenario,
            ScenarioRunConfig(
                demo_root=demo_root,
                dry_run=args.dry_run,
                model=args.model,
                sandbox=args.sandbox,
                save_thread=args.save_thread,
            ),
        )
    except CodexDependencyError as exc:
        raise SystemExit(str(exc)) from exc

    print(render_scenario_result(result))
    if args.visualize:
        html_path = _visualize_report(result.report_path, args.html_output)
        print()
        print(f"Wrote HTML report: {html_path}")
    if args.send:
        print()
        _send_report_notification(
            env_path=Path(args.env),
            report_path=result.report_path,
            scenario=result.scenario,
            timeout=args.timeout,
        )


def _demo_root_from_args(value: str | None) -> Path:
    if value:
        return Path(value).expanduser()
    return default_demo_root()


def _send_report_notification(
    *,
    env_path: Path,
    report_path: Path,
    scenario: str,
    timeout: float,
) -> None:
    env = load_env(env_path)
    webhook = resolve_wecom_webhook(env.get("WECOM_WEBHOOK_URL", ""), env.get("WECOM_WEBHOOK_KEY", ""))
    if not webhook:
        raise SystemExit("WECOM_WEBHOOK_URL or WECOM_WEBHOOK_KEY is not set; omit --send or configure .env.")

    content = build_notification_content(
        message=f"场景{scenario}测试报告已生成",
        report_path=report_path,
        title="AI Test Officer",
    )
    payload = build_wecom_payload(content, msgtype="markdown")
    result = send_wecom_payload(
        webhook.key,
        payload,
        timeout=timeout,
        base_url=webhook.base_url,
    )
    if not result.ok:
        detail = result.errmsg or "send failed"
        raise SystemExit(
            f"WeCom notification failed: status={result.status} errcode={result.errcode} {detail}"
        )

    print("Sent WeCom notification: errcode=0 errmsg=ok")


def _notify_from_args(args: argparse.Namespace) -> None:
    report_path = Path(args.report) if args.report else None
    if not args.message and not report_path:
        raise SystemExit("notify requires --message or --report")

    env = load_env(Path(args.env))
    try:
        webhook = resolve_wecom_webhook(
            env.get("WECOM_WEBHOOK_URL", ""),
            env.get("WECOM_WEBHOOK_KEY", ""),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    content = build_notification_content(
        message=args.message,
        report_path=report_path,
        title=args.title,
    )
    payload = build_wecom_payload(content, msgtype=args.msgtype)

    if args.dry_run:
        print(render_dry_run(payload, webhook))
        return

    if not webhook:
        raise SystemExit("WECOM_WEBHOOK_URL or WECOM_WEBHOOK_KEY is not set; run with --dry-run to simulate.")

    result = send_wecom_payload(
        webhook.key,
        payload,
        timeout=args.timeout,
        base_url=webhook.base_url,
    )
    if not result.ok:
        detail = result.errmsg or "send failed"
        raise SystemExit(f"WeCom notification failed: status={result.status} errcode={result.errcode} {detail}")

    print("Sent WeCom notification: errcode=0 errmsg=ok")


def _visualize_from_args(args: argparse.Namespace) -> None:
    report_path = Path(args.report)
    run_json_path = Path(args.run_json) if args.run_json else run_json_path_for(report_path)
    output_path = Path(args.output) if args.output else None
    html_path = visualize_report(report_path, run_json_path, output_path)
    print(f"Wrote HTML report: {html_path}")


def _visualize_report(report_path: Path, output: str | None) -> Path:
    output_path = Path(output) if output else None
    return visualize_report(report_path, run_json_path_for(report_path), output_path)
