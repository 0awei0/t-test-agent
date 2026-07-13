from __future__ import annotations

import argparse
import time
import urllib.parse
from pathlib import Path

from .agent import load_env_file, run_tool_call_smoke
from .agent.planner import AgentPlannerUnavailable
from .batch import BatchMrConfig, run_mr_batch
from .config import DEFAULT_AGENT_MAX_TURNS
from .demo import (
    DemoRunConfig,
    create_agent_loop_demo,
    create_fullstack_demo,
    create_investigation_demo,
    create_release_guard_demo,
    run_agent_loop_demo,
    run_fullstack_demo,
    run_investigation_demo,
    run_release_guard_demo,
)
from .execution.runner import RunConfig, run_test_officer
from .integrations.gongfeng import GongfengError
from .integrations.wecom import NotifyError, build_wecom_markdown, send_wecom_markdown
from .mcp import run_mcp_config_smoke
from .report_site import export_fue_static_project, publish_record, publish_report_path, serve_report_site
from .safety_smoke import run_safety_smoke
from .showcase_doctor import run_demo_doctor
from .tools.git import GitToolError
from .tools.safety import SafetyError


PASS_DEMO_SCENARIOS = ("release-guard-pass", "promotion-chain-pass", "refund-guard-pass")
INVESTIGATION_DEMO_SCENARIOS = ("promotion-chain", "refund-guard", "promotion-chain-pass", "refund-guard-pass")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ai-test-officer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run the Agents SDK AI Test Officer workflow.")
    run.add_argument("--repo", default=None, help="Read-only source repository or MR local checkout override.")
    run.add_argument("--git-range", default=None, help="Git range in <base>..<head> form.")
    run.add_argument("--mr-url", default=None, help="Read-only Gongfeng/TGit MR URL.")
    run.add_argument("--task", required=True, help="Testing request.")
    run.add_argument("--runs-root", default="runs", help="Local ignored run workspace root.")
    run.add_argument("--run-id", default=None, help="Optional deterministic run id.")
    run.add_argument("--env", default=".env", help="Local env file to load before running.")
    run.add_argument(
        "--max-agent-turns",
        type=int,
        default=DEFAULT_AGENT_MAX_TURNS,
        help="Maximum tool-calling turns for the Agent Planner.",
    )
    run.add_argument(
        "--planner-mode",
        choices=("auto", "agent", "agent-strict", "deterministic"),
        default="auto",
        help="Test planning mode. auto uses Agent Planner when a model is configured.",
    )
    run.add_argument(
        "--memory-mode",
        choices=("structured", "model"),
        default="structured",
        help="How to summarize run context for reports and model prompts.",
    )
    _add_mr_checkout_arg(run)
    run.add_argument("--send", action="store_true", help="Send a compact WeCom Markdown summary after the run.")
    _add_publish_args(run)
    run.add_argument(
        "--notify-dry-run",
        action="store_true",
        help="Render the WeCom payload without sending it.",
    )
    run.add_argument(
        "--allow-temp-test-code",
        action="store_true",
        help="Allow generated test code inside the isolated run workspace.",
    )
    run.add_argument(
        "--visualize",
        action="store_true",
        help="Start the live execution dashboard and stream this run in real time.",
    )
    run.add_argument("--dashboard-host", default="127.0.0.1", help="Host for the live dashboard server.")
    run.add_argument("--dashboard-port", type=int, default=8789, help="Port for the live dashboard server.")

    dashboard = subparsers.add_parser(
        "dashboard",
        help="Start the local task workbench and allow synthetic demos to run from the browser.",
    )
    dashboard.add_argument("--runs-root", default="runs/live-runs", help="Ignored root for browser-started runs.")
    dashboard.add_argument("--host", default="127.0.0.1", help="Local dashboard bind host.")
    dashboard.add_argument("--port", type=int, default=8789, help="Local dashboard port.")

    smoke = subparsers.add_parser("smoke", help="Run local smoke checks.")
    smoke_subparsers = smoke.add_subparsers(dest="smoke_command", required=True)
    tool_smoke = smoke_subparsers.add_parser("tools", help="Verify model function-calling tools.")
    tool_smoke.add_argument("--runs-root", default="runs", help="Local ignored run workspace root.")
    tool_smoke.add_argument("--run-id", default=None, help="Optional deterministic run id.")
    tool_smoke.add_argument("--env", default=".env", help="Local env file to load before running.")
    mcp_smoke = smoke_subparsers.add_parser("mcp", help="Verify project MCP config shape.")
    mcp_smoke.add_argument("--repo-root", default=".", help="Repository root containing .codex/config.toml.")
    safety_smoke = smoke_subparsers.add_parser("safety", help="Verify local tool safety guardrails.")
    safety_smoke.add_argument("--runs-root", default="runs", help="Local ignored run workspace root.")
    safety_smoke.add_argument("--run-id", default=None, help="Optional deterministic run id.")
    agent_loop_smoke = smoke_subparsers.add_parser("agent-loop", help="Run the agentic tool loop smoke demo.")
    agent_loop_smoke.add_argument(
        "--planner-mode",
        choices=("agent", "agent-strict"),
        default="agent-strict",
    )
    agent_loop_smoke.add_argument(
        "--memory-mode",
        choices=("structured", "model"),
        default="structured",
    )
    agent_loop_smoke.add_argument("--demo-root", default="runs/demos", help="Ignored demo repository root.")
    agent_loop_smoke.add_argument("--runs-root", default="runs", help="Local ignored run workspace root.")
    agent_loop_smoke.add_argument("--run-id", default=None, help="Optional deterministic run id.")
    agent_loop_smoke.add_argument("--env", default=".env", help="Local env file to load before running.")
    agent_loop_smoke.add_argument("--max-agent-turns", type=int, default=DEFAULT_AGENT_MAX_TURNS)

    demo = subparsers.add_parser("demo", help="Create or run synthetic validation demos.")
    demo_subparsers = demo.add_subparsers(dest="demo_command", required=True)
    demo_create = demo_subparsers.add_parser("create", help="Create a synthetic demo repository.")
    demo_create.add_argument(
        "--scenario",
        choices=("fullstack", "agent-loop", "release-guard", *PASS_DEMO_SCENARIOS, "promotion-chain", "refund-guard"),
        required=True,
    )
    demo_create.add_argument("--demo-root", default="runs/demos", help="Ignored demo repository root.")

    demo_doctor = demo_subparsers.add_parser("doctor", help="Check showcase/FUE/WeCom readiness.")
    demo_doctor.add_argument("--fue-public", default=None, help="FUE public directory to inspect.")
    demo_doctor.add_argument("--detail-url", default=None, help="Hosted report URL expected in WeCom.")
    demo_doctor.add_argument(
        "--require-detail-url",
        action="store_true",
        help="Fail when --detail-url is missing or not clickable.",
    )
    demo_doctor.add_argument(
        "--require-evidence",
        action="store_true",
        help="Fail when the public package has no image evidence.",
    )
    demo_doctor.add_argument("--env", default=".env", help="Local env file to load before checking.")

    demo_run = demo_subparsers.add_parser("run", help="Run a synthetic demo through AI Test Officer.")
    demo_run.add_argument(
        "--scenario",
        choices=("fullstack", "agent-loop", "release-guard", *PASS_DEMO_SCENARIOS, "promotion-chain", "refund-guard", "safety-guardrails"),
        required=True,
    )
    demo_run.add_argument("--demo-root", default="runs/demos", help="Ignored demo repository root.")
    demo_run.add_argument("--runs-root", default="runs", help="Local ignored run workspace root.")
    demo_run.add_argument("--run-id", default=None, help="Optional deterministic run id.")
    demo_run.add_argument("--env", default=".env", help="Local env file to load before running.")
    demo_run.add_argument("--max-agent-turns", type=int, default=DEFAULT_AGENT_MAX_TURNS)
    demo_run.add_argument(
        "--planner-mode",
        choices=("auto", "agent", "agent-strict", "deterministic"),
        default="auto",
        help="Test planning mode. auto uses Agent Planner when a model is configured.",
    )
    demo_run.add_argument(
        "--memory-mode",
        choices=("structured", "model"),
        default="structured",
        help="How to summarize run context for reports and model prompts.",
    )
    demo_run.add_argument(
        "--allow-temp-test-code",
        action="store_true",
        help="Allow generated test code inside the isolated run workspace.",
    )
    demo_run.add_argument("--send", action="store_true", help="Send a compact WeCom Markdown summary.")
    _add_publish_args(demo_run)
    demo_run.add_argument("--notify-dry-run", action="store_true", help="Render WeCom payload without sending.")
    demo_run.add_argument(
        "--visualize",
        action="store_true",
        help="Start the live execution dashboard and stream this run in real time.",
    )
    demo_run.add_argument("--dashboard-host", default="127.0.0.1", help="Host for the live dashboard server.")
    demo_run.add_argument("--dashboard-port", type=int, default=8789, help="Port for the live dashboard server.")

    demo_showcase = demo_subparsers.add_parser(
        "showcase",
        help="Run the competition showcase flow and optionally export FUE/notify WeCom.",
    )
    demo_showcase.add_argument(
        "--scenario",
        choices=("agent-loop", "fullstack", "release-guard", "promotion-chain", "refund-guard"),
        default="release-guard",
    )
    demo_showcase.add_argument("--demo-root", default="runs/demos", help="Ignored demo repository root.")
    demo_showcase.add_argument("--runs-root", default="runs", help="Local ignored run workspace root.")
    demo_showcase.add_argument("--run-id", default=None, help="Optional deterministic run id.")
    demo_showcase.add_argument("--env", default=".env", help="Local env file to load before running.")
    demo_showcase.add_argument("--max-agent-turns", type=int, default=DEFAULT_AGENT_MAX_TURNS)
    demo_showcase.add_argument(
        "--planner-mode",
        choices=("agent", "agent-strict", "deterministic"),
        default="agent-strict",
        help="Use agent-strict for the clearest Agent demo; deterministic is useful for offline rehearsal.",
    )
    demo_showcase.add_argument(
        "--memory-mode",
        choices=("structured", "model"),
        default="structured",
    )
    demo_showcase.add_argument(
        "--export-fue",
        default=None,
        help="Optional FUE static project output directory, for example runs/fue-site/agent-loop.",
    )
    _add_publish_args(demo_showcase)
    demo_showcase.add_argument("--project-slug", default="ai-test-officer-report")
    demo_showcase.add_argument("--project-name", default="AI Test Officer Report")
    demo_showcase.add_argument(
        "--detail-url",
        default=None,
        help="Already deployed report URL to include in the WeCom summary.",
    )
    demo_showcase.add_argument("--send", action="store_true", help="Send a compact WeCom Markdown summary.")
    demo_showcase.add_argument("--notify-dry-run", action="store_true", help="Render WeCom payload without sending.")

    report = subparsers.add_parser("report", help="Publish or serve generated HTML reports.")
    report_subparsers = report.add_subparsers(dest="report_command", required=True)
    report_publish = report_subparsers.add_parser("publish", help="Publish one report into a static site root.")
    report_publish.add_argument("--report", required=True, help="Path to runs/<run-id>/report.md.")
    report_publish.add_argument("--site-root", default="runs/report-site", help="Static report site root.")
    report_publish.add_argument("--base-url", default=None, help="Internal base URL exposed to WeCom users.")
    report_export_fue = report_subparsers.add_parser(
        "export-fue",
        help="Export one generated report as a FUE static Web application.",
    )
    report_export_fue.add_argument("--report", required=True, help="Path to runs/<run-id>/report.md.")
    report_export_fue.add_argument("--output", default=None, help="Output FUE project directory.")
    report_export_fue.add_argument("--project-slug", default="ai-test-officer-report")
    report_export_fue.add_argument("--project-name", default="AI Test Officer Report")
    report_serve = report_subparsers.add_parser("serve", help="Serve a static report site locally.")
    report_serve.add_argument("--root", default="runs/report-site", help="Static report site root.")
    report_serve.add_argument("--host", default="0.0.0.0")
    report_serve.add_argument("--port", type=int, default=8788)
    report_serve.add_argument(
        "--live",
        action="store_true",
        help="Serve the live dashboard for a finished run (replay mode).",
    )
    report_serve.add_argument("--run-id", default=None, help="Run id to replay with --live.")
    report_serve.add_argument("--runs-root", default="runs", help="Root containing runs/<run-id>.")

    batch = subparsers.add_parser("batch", help="Run batch validation jobs.")
    batch_subparsers = batch.add_subparsers(dest="batch_command", required=True)
    batch_mr = batch_subparsers.add_parser("mr", help="Run AI Test Officer over MR candidates.")
    batch_mr.add_argument("--candidate-file", required=True, help="Markdown file containing MR URLs.")
    batch_mr.add_argument("--runs-root", default="runs/real-mr-batch", help="Ignored batch output root.")
    batch_mr.add_argument("--env", default=".env", help="Local env file to load before running.")
    batch_mr.add_argument(
        "--task",
        default="真实MR验证：分析测试风险并执行本地安全验证",
        help="Task prompt used for each MR.",
    )
    batch_mr.add_argument(
        "--planner-mode",
        choices=("auto", "agent", "agent-strict", "deterministic"),
        default="agent",
    )
    batch_mr.add_argument(
        "--memory-mode",
        choices=("structured", "model"),
        default="structured",
    )
    batch_mr.add_argument("--allow-temp-test-code", action="store_true")
    batch_mr.add_argument("--max-agent-turns", type=int, default=DEFAULT_AGENT_MAX_TURNS)
    _add_mr_checkout_arg(batch_mr)
    batch_mr.add_argument("--limit", type=int, default=None)

    args = parser.parse_args(argv)
    if args.command == "run":
        _validate_run_args(parser, args)
        _run_from_args(args)
    elif args.command == "dashboard":
        server, _ = _start_task_dashboard(args.runs_root, args.host, args.port)
        _hold_dashboard(server)
    elif args.command == "smoke" and args.smoke_command == "tools":
        _smoke_tools_from_args(args)
    elif args.command == "smoke" and args.smoke_command == "mcp":
        _smoke_mcp_from_args(args)
    elif args.command == "smoke" and args.smoke_command == "safety":
        _smoke_safety_from_args(args)
    elif args.command == "smoke" and args.smoke_command == "agent-loop":
        _smoke_agent_loop_from_args(args)
    elif args.command == "demo" and args.demo_command == "create":
        _demo_create_from_args(args)
    elif args.command == "demo" and args.demo_command == "doctor":
        _demo_doctor_from_args(args)
    elif args.command == "demo" and args.demo_command == "run":
        _demo_run_from_args(args)
    elif args.command == "demo" and args.demo_command == "showcase":
        _demo_showcase_from_args(args)
    elif args.command == "report" and args.report_command == "publish":
        _report_publish_from_args(args)
    elif args.command == "report" and args.report_command == "export-fue":
        _report_export_fue_from_args(args)
    elif args.command == "report" and args.report_command == "serve":
        if args.live:
            if not args.run_id:
                raise SystemExit("--live requires --run-id")
            server, _ = _start_live_dashboard(args.run_id, args.runs_root, args.host, args.port)
            _hold_dashboard(server)
        else:
            serve_report_site(Path(args.root), host=args.host, port=args.port)
    elif args.command == "batch" and args.batch_command == "mr":
        _batch_mr_from_args(args)


def _run_from_args(args: argparse.Namespace) -> None:
    load_env_file(Path(args.env))
    run_id = args.run_id
    dashboard = None
    if args.visualize:
        run_id = run_id or f"live-{int(time.time())}"
        args.run_id = run_id
        dashboard, _ = _start_live_dashboard(run_id, args.runs_root, args.dashboard_host, args.dashboard_port)
    try:
        record = run_test_officer(
            RunConfig(
                repo=Path(args.repo) if args.repo else None,
                git_range=args.git_range,
                task=args.task,
                runs_root=Path(args.runs_root),
                allow_temp_test_code=args.allow_temp_test_code,
                run_id=run_id,
                mr_url=args.mr_url,
                planner_mode=args.planner_mode,
                memory_mode=args.memory_mode,
                max_agent_turns=args.max_agent_turns,
                mr_checkout_mode=args.mr_checkout_mode,
            )
        )
    except (AgentPlannerUnavailable, GitToolError, GongfengError, SafetyError, TimeoutError) as exc:
        if dashboard:
            _hold_dashboard(dashboard)
        raise SystemExit(f"ai-test-officer failed: {exc}") from exc

    _publish_from_args(record, args)
    if args.send or args.notify_dry_run:
        _warn_if_sending_without_detail_url(record, send=args.send)
        try:
            notify_result = send_wecom_markdown(
                build_wecom_markdown(record),
                dry_run=args.notify_dry_run,
            )
        except NotifyError as exc:
            raise SystemExit(f"ai-test-officer notification failed: {exc}") from exc
        if notify_result.dry_run:
            print(f"WeCom dry-run payload: {notify_result.body}")
        else:
            print(f"WeCom notification: delivered status={notify_result.status}")

    print(f"Run: {record.run_dir}")
    print(f"Report: {record.report_path}")
    print(f"JSON: {record.json_path}")
    print(f"HTML: {record.html_path}")
    if record.published_report_path:
        print(f"Published HTML: {record.published_report_path}")
    if record.detail_url:
        print(f"Detail URL: {record.detail_url}")
    print(f"Verdict: {record.verdict}")
    print(f"Planner: {record.planner_mode}")
    if dashboard:
        _hold_dashboard(dashboard)


def _demo_create_from_args(args: argparse.Namespace) -> None:
    if args.scenario == "fullstack":
        repo = create_fullstack_demo(Path(args.demo_root))
    elif args.scenario == "agent-loop":
        repo = create_agent_loop_demo(Path(args.demo_root))
    elif args.scenario in {"release-guard", "release-guard-pass"}:
        repo = create_release_guard_demo(Path(args.demo_root), repaired=args.scenario.endswith("-pass"))
    elif args.scenario in INVESTIGATION_DEMO_SCENARIOS:
        repo = create_investigation_demo(Path(args.demo_root), args.scenario)
    else:
        raise SystemExit(f"unsupported demo scenario: {args.scenario}")
    print(f"Demo: {repo}")
    print("Git range: HEAD~1..HEAD")


def _demo_doctor_from_args(args: argparse.Namespace) -> None:
    load_env_file(Path(args.env))
    result = run_demo_doctor(
        fue_public=Path(args.fue_public) if args.fue_public else None,
        detail_url=args.detail_url,
        require_detail_url=args.require_detail_url,
        require_evidence=args.require_evidence,
    )
    print(result.to_text())
    if not result.passed:
        raise SystemExit(1)


def _demo_run_from_args(args: argparse.Namespace) -> None:
    load_env_file(Path(args.env))
    run_id = args.run_id
    dashboard = None
    if args.visualize:
        run_id = run_id or f"live-{int(time.time())}"
        args.run_id = run_id
        dashboard, _ = _start_live_dashboard(run_id, args.runs_root, args.dashboard_host, args.dashboard_port)
    try:
        config = DemoRunConfig(
            demo_root=Path(args.demo_root),
            planner_mode=args.planner_mode,
            allow_temp_test_code=args.allow_temp_test_code,
            runs_root=Path(args.runs_root),
            run_id=run_id,
            memory_mode=args.memory_mode,
            max_agent_turns=args.max_agent_turns,
        )
        if args.scenario == "fullstack":
            record = run_fullstack_demo(config)
        elif args.scenario == "agent-loop":
            record = run_agent_loop_demo(config)
        elif args.scenario in {"release-guard", "release-guard-pass"}:
            record = run_release_guard_demo(config, repaired=args.scenario.endswith("-pass"))
        elif args.scenario in INVESTIGATION_DEMO_SCENARIOS:
            record = run_investigation_demo(config, args.scenario)
        elif args.scenario == "safety-guardrails":
            record = run_safety_smoke(runs_root=Path(args.runs_root), run_id=args.run_id).record
        else:
            raise SystemExit(f"unsupported demo scenario: {args.scenario}")
    except (AgentPlannerUnavailable, GitToolError, GongfengError, SafetyError, TimeoutError) as exc:
        raise SystemExit(f"ai-test-officer demo failed: {exc}") from exc

    _publish_from_args(record, args)
    if args.send or args.notify_dry_run:
        _warn_if_sending_without_detail_url(record, send=args.send)
        try:
            notify_result = send_wecom_markdown(
                build_wecom_markdown(record),
                dry_run=args.notify_dry_run,
            )
        except NotifyError as exc:
            raise SystemExit(f"ai-test-officer notification failed: {exc}") from exc
        if notify_result.dry_run:
            print(f"WeCom dry-run payload: {notify_result.body}")
        else:
            print(f"WeCom notification: delivered status={notify_result.status}")

    print(f"Run: {record.run_dir}")
    print(f"Report: {record.report_path}")
    print(f"JSON: {record.json_path}")
    print(f"HTML: {record.html_path}")
    if record.published_report_path:
        print(f"Published HTML: {record.published_report_path}")
    if record.detail_url:
        print(f"Detail URL: {record.detail_url}")
    print(f"Verdict: {record.verdict}")
    print(f"Planner: {record.planner_mode}")
    if dashboard:
        _hold_dashboard(dashboard)


def _demo_showcase_from_args(args: argparse.Namespace) -> None:
    load_env_file(Path(args.env))
    try:
        config = DemoRunConfig(
            demo_root=Path(args.demo_root),
            planner_mode=args.planner_mode,
            allow_temp_test_code=True,
            runs_root=Path(args.runs_root),
            run_id=args.run_id,
            memory_mode=args.memory_mode,
            max_agent_turns=args.max_agent_turns,
        )
        if args.scenario == "agent-loop":
            record = run_agent_loop_demo(config)
        elif args.scenario == "fullstack":
            record = run_fullstack_demo(config)
        elif args.scenario == "release-guard":
            record = run_release_guard_demo(config)
        elif args.scenario in {"promotion-chain", "refund-guard"}:
            record = run_investigation_demo(config, args.scenario)
        else:
            raise SystemExit(f"unsupported demo scenario: {args.scenario}")
    except (AgentPlannerUnavailable, GitToolError, GongfengError, SafetyError, TimeoutError) as exc:
        raise SystemExit(f"ai-test-officer showcase failed: {exc}") from exc

    _publish_from_args(record, args)

    if args.export_fue:
        exported = export_fue_static_project(
            record.report_path,
            output=Path(args.export_fue),
            project_slug=args.project_slug,
            project_name=args.project_name,
        )
        print(f"FUE project: {exported.project_root}")
        print(f"FUE public: {exported.public_dir}")
        print(f"FUE deploy doc: {exported.deploy_doc_path}")

    if args.detail_url:
        record.detail_url = args.detail_url

    if args.send or args.notify_dry_run:
        _require_showcase_detail_url(record, send=args.send)
        try:
            notify_result = send_wecom_markdown(
                build_wecom_markdown(record),
                dry_run=args.notify_dry_run,
            )
        except NotifyError as exc:
            raise SystemExit(f"ai-test-officer notification failed: {exc}") from exc
        if notify_result.dry_run:
            print(f"WeCom dry-run payload: {notify_result.body}")
        else:
            print(f"WeCom notification: delivered status={notify_result.status}")

    print(f"Run: {record.run_dir}")
    print(f"Report: {record.report_path}")
    print(f"JSON: {record.json_path}")
    print(f"HTML: {record.html_path}")
    print(f"Verdict: {record.verdict}")
    print(f"Planner: {record.planner_mode}")
    print(f"Required tool check: {record.required_tool_check.passed}")
    if record.required_tool_check.missing:
        print(f"Missing tools: {', '.join(record.required_tool_check.missing)}")


def _validate_run_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    has_mr = bool(args.mr_url)
    has_range = bool(args.repo and args.git_range)
    if has_mr and args.git_range:
        parser.error("--mr-url cannot be combined with --git-range")
    if not has_mr and not has_range:
        parser.error("run requires either --mr-url or both --repo and --git-range")


def _smoke_tools_from_args(args: argparse.Namespace) -> None:
    load_env_file(Path(args.env))
    try:
        result = run_tool_call_smoke(runs_root=Path(args.runs_root), run_id=args.run_id)
    except RuntimeError as exc:
        raise SystemExit(f"ai-test-officer smoke failed: {exc}") from exc

    print(f"Run: {result.run_dir}")
    print(f"JSON: {result.json_path}")
    print(f"Tool calls: {', '.join(result.tool_calls) or 'none'}")
    print(f"Passed: {result.passed}")
    print("Final output:")
    print(result.final_output)


def _smoke_mcp_from_args(args: argparse.Namespace) -> None:
    result = run_mcp_config_smoke(Path(args.repo_root))
    print(result.to_json())
    if not result.passed:
        raise SystemExit(1)


def _smoke_safety_from_args(args: argparse.Namespace) -> None:
    result = run_safety_smoke(runs_root=Path(args.runs_root), run_id=args.run_id)
    print(f"Run: {result.record.run_dir}")
    print(f"Report: {result.record.report_path}")
    print(f"JSON: {result.record.json_path}")
    print(f"HTML: {result.record.html_path}")
    print(f"Blocked: {result.blocked}")
    print(f"Allowed: {result.allowed}")
    print(f"Passed: {result.passed}")
    if not result.passed:
        raise SystemExit(1)


def _smoke_agent_loop_from_args(args: argparse.Namespace) -> None:
    load_env_file(Path(args.env))
    try:
        record = run_agent_loop_demo(
            DemoRunConfig(
                demo_root=Path(args.demo_root),
                planner_mode=args.planner_mode,
                allow_temp_test_code=True,
                runs_root=Path(args.runs_root),
                run_id=args.run_id,
                memory_mode=args.memory_mode,
                max_agent_turns=args.max_agent_turns,
            )
        )
    except (AgentPlannerUnavailable, GitToolError, GongfengError, SafetyError, TimeoutError) as exc:
        raise SystemExit(f"ai-test-officer smoke failed: {exc}") from exc
    print(f"Run: {record.run_dir}")
    print(f"Report: {record.report_path}")
    print(f"Required tool check: {record.required_tool_check.passed}")
    print(f"Tools: {', '.join(record.required_tool_check.observed)}")
    if record.required_tool_check.missing:
        print(f"Missing: {', '.join(record.required_tool_check.missing)}")
        raise SystemExit(1)


def _report_publish_from_args(args: argparse.Namespace) -> None:
    published = publish_report_path(
        Path(args.report),
        site_root=Path(args.site_root),
        base_url=args.base_url,
    )
    print(f"Site root: {published.site_root}")
    print(f"Published HTML: {published.index_path}")
    if published.detail_url:
        print(f"Detail URL: {published.detail_url}")


def _report_export_fue_from_args(args: argparse.Namespace) -> None:
    exported = export_fue_static_project(
        Path(args.report),
        output=Path(args.output) if args.output else None,
        project_slug=args.project_slug,
        project_name=args.project_name,
    )
    print(f"FUE project: {exported.project_root}")
    print(f"Static directory: {exported.public_dir}")
    print(f"Index: {exported.index_path}")
    print(f"Config: {exported.config_path}")
    print(f"Deploy doc: {exported.deploy_doc_path}")
    print(
        "Deploy to EdgeOne Makers: "
        f"cd {exported.public_dir} && PAGES_SOURCE=skills "
        f"edgeone makers deploy -n {args.project_slug} --json"
    )


def _batch_mr_from_args(args: argparse.Namespace) -> None:
    load_env_file(Path(args.env))
    summary = run_mr_batch(
        BatchMrConfig(
            candidate_file=Path(args.candidate_file),
            runs_root=Path(args.runs_root),
            task=args.task,
            planner_mode=args.planner_mode,
            memory_mode=args.memory_mode,
            allow_temp_test_code=args.allow_temp_test_code,
            max_agent_turns=args.max_agent_turns,
            mr_checkout_mode=args.mr_checkout_mode,
            limit=args.limit,
        )
    )
    ok_count = sum(1 for item in summary.results if item.status == "ok")
    error_count = sum(1 for item in summary.results if item.status == "error")
    print(f"Batch root: {summary.runs_root}")
    print(f"Summary: {summary.markdown_path}")
    print(f"JSON: {summary.json_path}")
    print(f"Total: {len(summary.results)} OK: {ok_count} Error: {error_count}")


def _add_publish_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--publish", action="store_true", help="Publish report.html to a static site root.")
    parser.add_argument("--site-root", default="runs/report-site", help="Static report site root.")
    parser.add_argument("--report-base-url", default=None, help="Internal base URL for the published report.")


def _add_mr_checkout_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--mr-checkout-mode",
        choices=("auto", "source-ref", "target-apply-diff", "diff-only"),
        default="auto",
        help="How MR exact code is prepared inside runs/<run-id>/repo.",
    )


def _start_live_dashboard(run_id: str, runs_root: str, host: str, port: int):
    from .live_server import serve_live

    server = serve_live(run_id=run_id, host=host, port=port, run_root=Path(runs_root))
    url = f"http://127.0.0.1:{port}/?run_id={urllib.parse.quote(run_id)}"
    print(f"Live dashboard: {url}")
    print("(Served on {host}:{port}; press Ctrl-C to stop.)".format(host=host, port=port))
    return server, url


def _start_task_dashboard(runs_root: str, host: str, port: int):
    from .live_server import serve_live

    server = serve_live(run_id="", host=host, port=port, run_root=Path(runs_root))
    url = f"http://127.0.0.1:{port}/"
    print(f"AI Test Officer task workbench: {url}")
    print("Select one synthetic TAPD/MR task, generate its plan, then click Start execution.")
    return server, url


def _hold_dashboard(server) -> None:
    try:
        while not server.shutdown_evt.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown_evt.set()
        try:
            server.shutdown()
        except KeyboardInterrupt:
            pass


def _publish_from_args(record, args: argparse.Namespace) -> None:
    if not args.publish:
        return
    published = publish_record(
        record,
        site_root=Path(args.site_root),
        base_url=args.report_base_url,
    )
    if args.report_base_url and not published.detail_url:
        raise SystemExit("failed to build report detail URL")


def _warn_if_sending_without_detail_url(record, *, send: bool) -> None:
    if send and not record.detail_url:
        print("Warning: sending WeCom without a clickable detail URL; pass --publish --report-base-url or --detail-url when sharing.")


def _require_showcase_detail_url(record, *, send: bool) -> None:
    if send and not record.detail_url:
        raise SystemExit(
            "demo showcase --send requires a clickable report URL. "
            "Deploy the FUE export first, then rerun with --detail-url <FUE URL> --send."
        )


if __name__ == "__main__":
    main()
