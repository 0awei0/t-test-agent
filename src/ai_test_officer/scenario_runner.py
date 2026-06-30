from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .codex_runner import CodexDependencyError, CodexRunner
from .demo_scenarios import ScenarioDemo, ensure_all_scenario_demos, ensure_scenario_demo
from .git_diff import collect_last_commit_diff
from .models import TestTask
from .prompts import build_test_officer_prompt
from .report import dry_run_report, write_report


SCENARIO_KEYS = ("A", "A-fullstack", "B", "C")


@dataclass(frozen=True)
class ScenarioRunConfig:
    demo_root: Path
    dry_run: bool
    model: str | None = None
    sandbox: str = "workspace_write"
    save_thread: bool = False


@dataclass(frozen=True)
class ScenarioRunResult:
    scenario: str
    demo: ScenarioDemo
    report_path: Path
    mode: str


def create_scenario_demos(root: Path, scenario: str) -> dict[str, ScenarioDemo]:
    if scenario.lower() == "all":
        return ensure_all_scenario_demos(root)

    demo = ensure_scenario_demo(root, scenario)
    return {demo.key: demo}


def run_scenario(scenario: str, config: ScenarioRunConfig) -> ScenarioRunResult:
    demo = ensure_scenario_demo(config.demo_root, scenario)
    task = task_for_demo(demo)
    prompt = build_test_officer_prompt(task)

    if config.dry_run:
        body = dry_run_report(prompt)
        mode = "dry-run"
    else:
        body = CodexRunner(
            model=config.model,
            sandbox=config.sandbox,
            ephemeral=not config.save_thread,
            auto_archive=not config.save_thread,
        ).run(prompt, task.resolved_repo())
        mode = "codex-sdk"

    report_path = write_report(task, body, dry_run=config.dry_run, scenario=demo.key)
    return ScenarioRunResult(demo.key, demo, report_path, mode)


def task_for_demo(demo: ScenarioDemo) -> TestTask:
    local_diff = collect_last_commit_diff(demo.repo_path) if demo.use_last_commit else None
    return TestTask(
        task=demo.task,
        repo_path=demo.repo_path,
        diff_text=local_diff.diff if local_diff else None,
        diff_label=local_diff.label if local_diff else None,
        changed_files=local_diff.name_status if local_diff else None,
        requirement_path=demo.requirement_path,
        output_path=Path(f"reports/scenario-{demo.key.lower()}-report.md"),
    )


def render_created_demos(demos: dict[str, ScenarioDemo]) -> str:
    lines: list[str] = []
    for key in SCENARIO_KEYS:
        demo = demos.get(key)
        if not demo:
            continue
        lines.append(f"Scenario {key}: {demo.repo_path}")
        if demo.requirement_path:
            lines.append(f"  Requirement: {demo.requirement_path}")
    return "\n".join(lines)


def render_scenario_result(result: ScenarioRunResult) -> str:
    return "\n".join(
        [
            f"Scenario {result.scenario} completed ({result.mode}).",
            f"Report: {result.report_path}",
            "",
            report_preview(result.report_path),
        ]
    )


def report_preview(path: Path, max_chars: int = 1200) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [
        line
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("<!--")
    ]
    preview = "\n".join(lines)
    if len(preview) <= max_chars:
        return preview
    return f"{preview[: max_chars - 18].rstrip()}\n...更多内容见完整报告。"


__all__ = [
    "CodexDependencyError",
    "SCENARIO_KEYS",
    "ScenarioRunConfig",
    "ScenarioRunResult",
    "create_scenario_demos",
    "render_created_demos",
    "render_scenario_result",
    "run_scenario",
    "task_for_demo",
]
