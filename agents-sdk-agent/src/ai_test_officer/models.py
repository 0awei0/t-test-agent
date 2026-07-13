from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .events import EventSink


FailureCategory = str
PlannerMode = str


@dataclass(frozen=True)
class ChangedFile:
    status: str
    path: str


@dataclass(frozen=True)
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    log_path: Path


@dataclass(frozen=True)
class GeneratedFile:
    path: Path
    reason: str


@dataclass(frozen=True)
class AgentTurn:
    turn: int
    tool: str
    input_summary: str
    output_summary: str
    model_initiated: bool = True


@dataclass
class RequiredToolCheck:
    required: list[str] = field(default_factory=list)
    observed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    passed: bool = True


@dataclass
class MemorySummary:
    mode: str = "structured"
    source_chars: int = 0
    summary_chars: int = 0
    compression_ratio: float = 1.0
    summary_path: Path | None = None
    artifact_paths: list[Path] = field(default_factory=list)
    used_model: bool = False
    status: str = "not-built"


@dataclass(frozen=True)
class SafetyCheck:
    name: str
    action: str
    target: str
    status: str
    blocked_by: str
    reason: str


@dataclass
class RunRecord:
    run_id: str
    task: str
    source_repo: Path
    workspace_repo: Path
    run_dir: Path
    git_range: str
    changed_files: list[ChangedFile]
    diff_text: str
    allow_temp_test_code: bool
    mr_url: str | None = None
    mr_project: str | None = None
    mr_iid: int | None = None
    mr_title: str | None = None
    checkout_strategy: str = "local-git-range"
    checkout_status: str = "ready"
    checkout_error: str = ""
    context_strategy: str = ""
    context_summary: str = ""
    context_dir: Path | None = None
    diff_index_path: Path | None = None
    skill_used: bool = False
    skill_path: Path | None = None
    skill_instructions: str = ""
    mcp_config_path: Path | None = None
    mcp_servers: list[str] = field(default_factory=list)
    planner_mode: PlannerMode = "deterministic"
    planner_trace: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    agent_turns: list[AgentTurn] = field(default_factory=list)
    required_tool_check: RequiredToolCheck = field(default_factory=RequiredToolCheck)
    memory_summary: MemorySummary = field(default_factory=MemorySummary)
    safety_checks: list[SafetyCheck] = field(default_factory=list)
    failure_category: FailureCategory = "no-test-selected"
    blocked_reason: str = ""
    generated_files: list[GeneratedFile] = field(default_factory=list)
    evidence_files: list[Path] = field(default_factory=list)
    commands: list[CommandResult] = field(default_factory=list)
    verdict: str = "needs-follow-up"
    risk: str = "medium"
    summary: str = ""
    change_intent: str = ""
    risk_findings: list[str] = field(default_factory=list)
    strategy_rationale: list[str] = field(default_factory=list)
    coverage_scope: list[str] = field(default_factory=list)
    untested_scope: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    agent_final_output: str = ""
    detail_url: str | None = None
    published_report_path: Path | None = None
    events: EventSink | None = None

    @property
    def report_path(self) -> Path:
        return self.run_dir / "report.md"

    @property
    def json_path(self) -> Path:
        return self.run_dir / "run.json"

    @property
    def html_path(self) -> Path:
        return self.run_dir / "report.html"
