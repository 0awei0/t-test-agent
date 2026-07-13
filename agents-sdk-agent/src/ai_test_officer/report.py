from __future__ import annotations

import html
import json
import re
from pathlib import Path

from .models import RunRecord
from .execution.failure import classify_command_failure
from .redaction import redact_secrets


def finalize_record(record: RunRecord) -> RunRecord:
    failures = [command for command in record.commands if command.returncode != 0]
    if failures:
        record.verdict = "fail"
        record.risk = "high"
        record.summary = f"隔离测试工作区内有 {len(failures)} 条测试命令失败。"
    elif record.commands:
        record.verdict = "pass"
        record.risk = "low"
        record.summary = "隔离测试工作区内的定向本地验证已通过。"
    else:
        record.verdict = "needs-follow-up"
        record.risk = "medium"
        record.summary = "本次变更没有选出可安全执行的定向测试命令。"
    return record


def populate_decision_context(record: RunRecord) -> RunRecord:
    if not isinstance(record.change_intent, str) or not record.change_intent:
        record.change_intent = f"依据测试任务，本次验证目标为：{record.task.strip()}"
    if not isinstance(record.risk_findings, list) or not record.risk_findings:
        record.risk_findings = _deterministic_risk_findings(record)
    if not isinstance(record.strategy_rationale, list) or not record.strategy_rationale:
        planner = "模型自主规划" if record.planner_mode in {"agent", "agent-strict"} else "确定性安全规划"
        record.strategy_rationale = [
            f"使用{planner}选择与变更文件直接相关的本地测试命令。",
            "所有命令只在隔离副本中执行，并受测试白名单约束。",
        ]
        if record.generated_files:
            record.strategy_rationale.append("允许 Agent 在隔离工作区补充临时边界测试，不修改原始仓库。")
    if not isinstance(record.coverage_scope, list) or not record.coverage_scope:
        record.coverage_scope = _deterministic_coverage_scope(record)
    if not isinstance(record.untested_scope, list) or not record.untested_scope:
        record.untested_scope = _deterministic_untested_scope(record)
    if not isinstance(record.recommendations, list) or not record.recommendations:
        record.recommendations = _deterministic_recommendations(record)
    return record


def _deterministic_risk_findings(record: RunRecord) -> list[str]:
    findings: list[str] = []
    for item in record.changed_files[:5]:
        suffix = Path(item.path).suffix.lower()
        if suffix in {".py", ".go", ".rs", ".ts", ".tsx", ".js", ".jsx"}:
            reason = "可执行逻辑发生变化，需要定向回归"
        elif "test" in item.path.lower():
            reason = "测试资产变化可能改变覆盖范围或回归信号"
        else:
            reason = "变更影响需结合上下文与执行证据确认"
        findings.append(f"{item.status} {item.path}：{reason}。")
    for command in record.commands:
        if command.returncode != 0:
            findings.append(
                f"{command.command} 执行失败，分类为 {classify_command_failure(command)[0]}。"
            )
    return findings or ["没有足够的变更或执行证据生成具体风险项。"]


def _deterministic_coverage_scope(record: RunRecord) -> list[str]:
    scope = [f"检查 {len(record.changed_files)} 个变更文件并建立风险地图。"]
    if record.commands:
        scope.append(f"执行 {len(record.commands)} 条白名单测试命令并保存完整日志。")
    if record.generated_files:
        scope.append(f"生成 {len(record.generated_files)} 个隔离临时测试文件。")
    if record.evidence_files:
        scope.append(f"采集 {len(record.evidence_files)} 个可复核证据文件。")
    return scope


def _deterministic_untested_scope(record: RunRecord) -> list[str]:
    gaps: list[str] = []
    if not record.commands:
        gaps.append("未选出可安全执行的测试命令。")
    if not record.generated_files:
        gaps.append("本次未生成额外的临时边界测试。")
    if not any(item.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} for item in record.evidence_files):
        gaps.append("未获得浏览器截图证据；前端体验仍需人工或 Playwright 补充确认。")
    if record.checkout_status != "ready":
        gaps.append("精确代码准备未完成，结论仅基于可用上下文。")
    return gaps or ["本次计划内的定向验证均已执行；更大范围回归不在当前任务范围内。"]


def _deterministic_recommendations(record: RunRecord) -> list[str]:
    if record.failure_category in {"dependency-missing", "environment-missing", "checkout-blocked"}:
        primary = "先补齐依赖或运行环境，再重新执行相同验证，当前结果不能证明业务回归。"
    elif record.failure_category == "agent-incomplete":
        primary = "修复模型或工具配置并重新运行 agent-strict，当前 Agent 闭环不完整。"
    elif record.verdict == "fail":
        primary = "在失败命令的根因被修复并通过同一组回归前，阻断本次发布。"
    elif record.verdict == "pass":
        primary = "定向验证已通过；结合未覆盖范围决定是否补充更大范围回归。"
    else:
        primary = "补充可执行的定向测试和证据后再做发布判断。"
    return [
        primary,
        "对外分享前复核公开报告和证据的脱敏结果。",
        "真实 MR 验证继续保留在隔离的 runs/<run-id>/ 工作区内。",
    ]


def write_outputs(record: RunRecord, agent_summary: str | None = None) -> None:
    populate_decision_context(record)
    record.run_dir.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(record, agent_summary)
    record.report_path.write_text(markdown, encoding="utf-8")
    record.json_path.write_text(_to_json(record), encoding="utf-8")
    record.html_path.write_text(render_html(markdown, record=record), encoding="utf-8")
    if record.events is not None:
        record.events.verdict(
            verdict=record.verdict,
            risk=record.risk,
            failure_category=record.failure_category,
            summary=record.summary,
        )
        record.events.done()


def render_markdown(record: RunRecord, agent_summary: str | None = None) -> str:
    populate_decision_context(record)
    changed = "\n".join(f"- {item.status}\t{item.path}" for item in record.changed_files) or "- 无"
    generated = (
        "\n".join(f"- {item.path.relative_to(record.run_dir)}: {item.reason}" for item in record.generated_files)
        or "- 无"
    )
    evidence = _evidence_block(record)
    commands = "\n".join(_command_line(record, item) for item in record.commands) or "- 无"
    mr = _mr_block(record)
    context = _context_block(record)
    planner = _planner_block(record)
    memory = _memory_block(record)
    safety = _safety_block(record)
    findings = _findings(record)
    decision_context = _decision_context_block(record)
    agent_decision_text = redact_secrets(record.agent_final_output.strip())
    agent_decision = f"\n## Agent 判断\n{agent_decision_text}\n" if agent_decision_text else ""
    agent_block = f"\n## Agent 总结\n{agent_summary}\n" if agent_summary else ""
    return f"""# AI 测试官报告

## 摘要
- 结论: {record.verdict}
- 风险: {record.risk}
- {record.summary}
{agent_decision}

## 决策依据
{decision_context}

## 范围
{mr}
- 源仓库: `{record.source_repo}`
- 隔离工作区: `{record.workspace_repo}`
- Git 范围: `{record.git_range}`
- 代码准备策略: `{record.checkout_strategy}`
- 代码准备状态: `{record.checkout_status}`
- 代码准备错误: {record.checkout_error or "无"}
- 临时测试代码: {"已启用" if record.allow_temp_test_code else "未启用"}
- Skill 已加载: `{record.skill_used}`
- MCP 服务: `{", ".join(record.mcp_servers) if record.mcp_servers else "无"}`

## 测试规划
{planner}

## 上下文
{context}

## 记忆压缩
{memory}

## 安全边界
{safety}

## 变更文件 / 风险地图
{changed}

## Agent 生成的临时测试
{generated}

## 执行结果
{commands}

## 证据
{evidence}

## 发现
{findings}

## 建议下一步
{_markdown_list(record.recommendations)}
{agent_block}"""


def _decision_context_block(record: RunRecord) -> str:
    return "\n".join(
        [
            "### 变更意图",
            record.change_intent,
            "",
            "### 主要风险",
            _markdown_list(record.risk_findings),
            "",
            "### 策略取舍",
            _markdown_list(record.strategy_rationale),
            "",
            "### 已覆盖范围",
            _markdown_list(record.coverage_scope),
            "",
            "### 未覆盖范围",
            _markdown_list(record.untested_scope),
        ]
    )


def _markdown_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or "- 无"


def render_html(markdown: str, *, record: RunRecord | None = None) -> str:
    if record is not None:
        return _render_structured_html(record, markdown)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>AI 测试官报告</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f6f8fb; color: #18212f; }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 32px; }}
    pre {{ white-space: pre-wrap; background: #101827; color: #e7edf7; padding: 24px; border-radius: 8px; line-height: 1.55; }}
  </style>
</head>
<body><main><pre>{html.escape(markdown)}</pre></main></body>
</html>
"""


def _findings(record: RunRecord) -> str:
    failures = [command for command in record.commands if command.returncode != 0]
    if not record.commands:
        return "- 未执行命令，因为没有选出可安全执行的定向测试命令。"
    if not failures:
        return "- 未观察到失败的定向测试命令。"
    return "\n".join(
        f"- `{item.command}` 失败：{_failure_excerpt(item)} "
        f"请查看 `{item.log_path.relative_to(record.run_dir)}`。"
        for item in failures
    )


def _to_json(record: RunRecord) -> str:
    def path(value: Path | None) -> str | None:
        return str(value) if value is not None else None

    data = {
        "run_id": record.run_id,
        "task": record.task,
        "source_repo": str(record.source_repo),
        "workspace_repo": str(record.workspace_repo),
        "run_dir": str(record.run_dir),
        "git_range": record.git_range,
        "mr_url": record.mr_url,
        "mr_project": record.mr_project,
        "mr_iid": record.mr_iid,
        "mr_title": record.mr_title,
        "checkout_strategy": record.checkout_strategy,
        "checkout_status": record.checkout_status,
        "checkout_error": record.checkout_error,
        "changed_files": [item.__dict__ for item in record.changed_files],
        "diff_text": None,
        "diff_index_path": path(record.diff_index_path),
        "context_dir": path(record.context_dir),
        "context_strategy": record.context_strategy,
        "context_summary_path": str(record.run_dir / "context" / "context_summary.md"),
        "skill_used": record.skill_used,
        "skill_path": path(record.skill_path),
        "mcp_config_path": path(record.mcp_config_path),
        "mcp_servers": record.mcp_servers,
        "planner_mode": record.planner_mode,
        "planner_trace": record.planner_trace,
        "tools_used": record.tools_used,
        "agent_turns": [
            {
                "turn": item.turn,
                "tool": item.tool,
                "input_summary": item.input_summary,
                "output_summary": item.output_summary,
                "model_initiated": item.model_initiated,
            }
            for item in record.agent_turns
        ],
        "required_tool_check": {
            "required": record.required_tool_check.required,
            "observed": record.required_tool_check.observed,
            "missing": record.required_tool_check.missing,
            "passed": record.required_tool_check.passed,
        },
        "memory_summary": {
            "mode": record.memory_summary.mode,
            "source_chars": record.memory_summary.source_chars,
            "summary_chars": record.memory_summary.summary_chars,
            "compression_ratio": record.memory_summary.compression_ratio,
            "summary_path": path(record.memory_summary.summary_path),
            "artifact_paths": [str(item) for item in record.memory_summary.artifact_paths],
            "used_model": record.memory_summary.used_model,
            "status": record.memory_summary.status,
        },
        "compression_ratio": record.memory_summary.compression_ratio,
        "safety_checks": [
            {
                "name": item.name,
                "action": item.action,
                "target": item.target,
                "status": item.status,
                "blocked_by": item.blocked_by,
                "reason": item.reason,
            }
            for item in record.safety_checks
        ],
        "failure_category": record.failure_category,
        "blocked_reason": record.blocked_reason,
        "agent_final_output": redact_secrets(record.agent_final_output),
        "allow_temp_test_code": record.allow_temp_test_code,
        "generated_files": [
            {"path": str(item.path), "reason": item.reason} for item in record.generated_files
        ],
        "evidence_files": [str(item) for item in record.evidence_files],
        "commands": [
            {
                "command": item.command,
                "returncode": item.returncode,
                "stdout": redact_secrets(item.stdout),
                "stderr": redact_secrets(item.stderr),
                "log_path": str(item.log_path),
                "failure_category": classify_command_failure(item)[0] if item.returncode != 0 else "passed",
            }
            for item in record.commands
        ],
        "verdict": record.verdict,
        "risk": record.risk,
        "summary": record.summary,
        "change_intent": record.change_intent,
        "risk_findings": record.risk_findings,
        "strategy_rationale": record.strategy_rationale,
        "coverage_scope": record.coverage_scope,
        "untested_scope": record.untested_scope,
        "recommendations": record.recommendations,
        "detail_url": record.detail_url,
        "published_report_path": path(record.published_report_path),
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def _failure_excerpt(item) -> str:
    text = redact_secrets((item.stderr or item.stdout).strip())
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return f"{stripped[:240]}."
    return "未捕获命令输出。"


def _command_line(record: RunRecord, item) -> str:
    category = classify_command_failure(item)[0] if item.returncode != 0 else "passed"
    return (
        f"- `{item.command}` -> 退出码 {item.returncode}; 分类: `{category}`; "
        f"日志: `{item.log_path.relative_to(record.run_dir)}`"
    )


def _mr_block(record: RunRecord) -> str:
    if not record.mr_url:
        return "- 输入: 本地 Git 范围"
    return (
        f"- MR: `{record.mr_project}!{record.mr_iid}`\n"
        f"- MR 标题: {record.mr_title or ''}\n"
        f"- MR URL: {record.mr_url}"
    )


def _context_block(record: RunRecord) -> str:
    lines = [
        f"- 策略: `{record.context_strategy or 'unknown'}`",
    ]
    if record.context_dir:
        lines.append(f"- 上下文目录: `{record.context_dir.relative_to(record.run_dir)}`")
    if record.diff_index_path:
        lines.append(f"- Diff 索引: `{record.diff_index_path.relative_to(record.run_dir)}`")
    if record.context_summary:
        lines.append("")
        lines.append(record.context_summary.strip())
    return "\n".join(lines)


def _memory_block(record: RunRecord) -> str:
    summary_path = _relative_or_raw(record, record.memory_summary.summary_path)
    artifacts = ", ".join(_relative_or_raw(record, item) for item in record.memory_summary.artifact_paths[:8])
    if len(record.memory_summary.artifact_paths) > 8:
        artifacts += f", +{len(record.memory_summary.artifact_paths) - 8} more"
    return "\n".join(
        [
            f"- 模式: `{record.memory_summary.mode}`",
            f"- 状态: `{record.memory_summary.status}`",
            f"- 原始字符数: `{record.memory_summary.source_chars}`",
            f"- 摘要字符数: `{record.memory_summary.summary_chars}`",
            f"- 压缩比例: `{record.memory_summary.compression_ratio}`",
            f"- 摘要路径: `{summary_path}`",
            f"- 关联产物: `{artifacts or '无'}`",
        ]
    )


def _planner_block(record: RunRecord) -> str:
    tools = ", ".join(record.tools_used[:12]) or "无"
    if len(record.tools_used) > 12:
        tools += f", +{len(record.tools_used) - 12} more"
    trace = "\n".join(f"- {item}" for item in record.planner_trace[:20]) or "- 无"
    if len(record.planner_trace) > 20:
        trace += f"\n- ... +{len(record.planner_trace) - 20} more"
    lines = [
        f"- 模式: `{record.planner_mode}`",
        f"- 失败分类: `{record.failure_category}`",
        f"- 阻塞原因: {record.blocked_reason or '无'}",
        f"- 已用工具: {tools}",
        f"- 关键工具检查: `{record.required_tool_check.passed}`",
        f"- 缺失关键工具: `{', '.join(record.required_tool_check.missing) if record.required_tool_check.missing else '无'}`",
        "",
        "### 规划轨迹",
        trace,
    ]
    return "\n".join(lines)


def _safety_block(record: RunRecord) -> str:
    if not record.safety_checks:
        return "\n".join(
            [
                "- 原始仓库只读；验证只在隔离的 `runs/<run-id>/repo/` 中执行。",
                "- 测试命令受项目白名单限制。",
                "- 临时写入仅允许测试和证据路径。",
                "- 本次运行未观察到被阻断动作。",
            ]
        )
    return "\n".join(
        f"- `{item.name}` {item.status}: `{item.action}` 目标 `{item.target}`; "
        f"阻断策略: `{item.blocked_by or '无'}`; 原因: {item.reason}"
        for item in record.safety_checks
    )


def _evidence_block(record: RunRecord) -> str:
    if not record.evidence_files:
        return "- 无"
    lines = []
    for item in record.evidence_files:
        try:
            rendered = item.relative_to(record.run_dir)
        except ValueError:
            rendered = item
        lines.append(f"- `{rendered}`")
    return "\n".join(lines)


def _render_structured_html(record: RunRecord, markdown: str) -> str:
    populate_decision_context(record)
    verdict_class = "fail" if record.verdict == "fail" else "pass" if record.verdict == "pass" else "warn"
    audience = _audience_context(record)
    findings = _html_findings(record)
    generated = _html_generated_files(record)
    recommended = _html_recommended_action(record)
    agent_decision = _html_agent_decision(record)
    sandbox = _html_sandbox(record)
    risk_items = _html_text_list(record.risk_findings)
    strategy_items = _html_text_list(record.strategy_rationale)
    coverage_items = _html_text_list(record.coverage_scope)
    untested_items = _html_text_list(record.untested_scope)
    recommendation_items = _html_text_list(record.recommendations)
    changed = "".join(
        f"<li><code>{html.escape(item.status)}</code> {html.escape(item.path)}</li>"
        for item in record.changed_files
    ) or "<li>无</li>"
    commands = "".join(
        "<li>"
        f"<code>{html.escape(item.command)}</code>"
        f"<span>exit {item.returncode}</span>"
        f"<span>{html.escape(classify_command_failure(item)[0] if item.returncode else 'passed')}</span>"
        "</li>"
        for item in record.commands
    ) or "<li>无</li>"
    command_failures = sum(1 for item in record.commands if item.returncode != 0)
    temp_test_label = "是" if record.generated_files else "否"
    required_label = "通过" if record.required_tool_check.passed else "未通过"
    safety = "".join(
        "<li>"
        f"<b>{html.escape(item.name)}</b>"
        f"<span>{html.escape(item.action)}</span>"
        f"<span>{html.escape(item.status)}</span>"
        f"<span>{html.escape(item.blocked_by or 'none')}</span>"
        f"<span>{html.escape(item.reason)}</span>"
        "</li>"
        for item in record.safety_checks
    ) or "<li><b>策略</b><span>原始仓库只读；命令和写入均受白名单限制。</span><span>active</span><span>local_safety_policy</span><span>未观察到被阻断动作。</span></li>"
    evidence = _html_evidence(record)
    sanitized_markdown = _sanitize_markdown_for_html(record, markdown)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI 测试官报告</title>
  <style>
    :root {{ color-scheme: light; }}
    *, *::before, *::after {{ box-sizing: border-box; }}
    html, body {{ max-width: 100%; overflow-x: clip; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #eef3f8; color: #172033; font-size: 15px; line-height: 1.55; }}
    main {{ width: min(1120px, 100%); margin: 0 auto; padding: 28px; }}
    h1, h2 {{ margin: 0 0 14px; letter-spacing: 0; }}
    h1 {{ font-size: 34px; line-height: 1.12; }}
    h2 {{ font-size: 22px; }}
    .hero {{ background: #132238; color: #f7fbff; border-radius: 8px; padding: 28px; margin-bottom: 18px; }}
    .hero p {{ max-width: 880px; margin: 12px 0 0; color: #d9e5f2; }}
    .launcher-link {{ display: inline-block; margin-top: 18px; padding: 10px 14px; border: 1px solid #8ab4f8; border-radius: 8px; color: #fff; font-weight: 700; text-decoration: none; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(145px, 1fr)); gap: 12px; margin-top: 20px; }}
    .metric {{ background: rgba(255,255,255,.09); border: 1px solid rgba(255,255,255,.16); border-radius: 8px; padding: 13px; min-height: 62px; }}
    .metric b {{ display: block; font-size: 12px; opacity: .78; margin-bottom: 8px; }}
    .badge {{ display: inline-block; border-radius: 999px; padding: 4px 10px; font-weight: 700; }}
    .badge.fail {{ background: #ffe1df; color: #9b1c16; }}
    .badge.pass {{ background: #ddf8e8; color: #126434; }}
    .badge.warn {{ background: #fff1cf; color: #765000; }}
    .band {{ display: grid; grid-template-columns: 1.2fr .8fr; gap: 14px; }}
    section {{ min-width: 0; background: #fff; border: 1px solid #d9e1ec; border-radius: 8px; padding: 18px; margin: 14px 0; }}
    ul {{ margin: 0; padding-left: 20px; }}
    li {{ margin: 7px 0; }}
    code {{ background: #eef3f8; color: #b3261e; padding: 1px 5px; border-radius: 4px; overflow-wrap: anywhere; word-break: break-word; }}
    .compact-list li {{ margin: 5px 0; }}
    .proof-list li {{ margin: 7px 0; }}
    .agent-decision > :first-child {{ margin-top: 0; }}
    .agent-decision > :last-child {{ margin-bottom: 0; }}
    .agent-decision pre {{ max-width: 100%; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; background: #111827; color: #edf2f7; padding: 14px; border-radius: 8px; overflow: auto; }}
    .agent-decision blockquote {{ margin: 12px 0; padding: 10px 14px; border-left: 4px solid #8ab4f8; background: #f4f8ff; color: #334155; }}
    .markdown-table {{ overflow-x: auto; }}
    .markdown-table table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    .markdown-table th, .markdown-table td {{ border: 1px solid #d9e1ec; padding: 9px 10px; text-align: left; vertical-align: top; overflow-wrap: anywhere; word-break: break-word; }}
    .markdown-table th {{ background: #f4f7fb; }}
    .tool-chain {{ display: flex; flex-wrap: wrap; gap: 8px; padding-left: 0; list-style: none; }}
    .tool-chain li {{ border: 1px solid #d9e1ec; border-radius: 999px; padding: 5px 10px; margin: 0; background: #f7fafc; }}
    .tool-chain .missing {{ background: #fff1f0; border-color: #ffc9c4; color: #9b1c16; }}
    .commands li {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
    .sandbox-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; }}
    .sandbox-card {{ border: 1px solid #d9e1ec; border-radius: 8px; padding: 12px; background: #fbfdff; }}
    .sandbox-card b {{ display: block; margin-bottom: 7px; }}
    .safety-list li {{ display: grid; grid-template-columns: 180px 1.2fr 90px 140px 1.8fr; gap: 10px; align-items: start; }}
    .muted {{ color: #64748b; }}
    .evidence-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }}
    .evidence img {{ width: 100%; border: 1px solid #d9e1ec; border-radius: 8px; background: #fff; }}
    .evidence-trigger {{ display: block; width: 100%; padding: 0; border: 0; background: transparent; cursor: zoom-in; }}
    .evidence-trigger:focus-visible {{ outline: 3px solid #8ab4f8; outline-offset: 2px; }}
    .evidence-modal {{ position: fixed; z-index: 20; inset: 0; display: grid; place-items: center; padding: 20px; background: rgba(8, 16, 31, .78); }}
    .evidence-modal[hidden] {{ display: none; }}
    .evidence-modal-content {{ position: relative; width: min(1040px, 100%); max-height: 100%; overflow: auto; padding: 46px 14px 14px; border-radius: 14px; background: #fff; box-shadow: 0 24px 72px rgba(0, 0, 0, .36); }}
    .evidence-modal-content img {{ display: block; width: auto; max-width: 100%; max-height: calc(100vh - 130px); margin: 0 auto; border-radius: 8px; }}
    .evidence-modal-content p {{ margin: 10px 4px 0; color: #64748b; font-size: 12px; overflow-wrap: anywhere; }}
    .evidence-modal-close {{ position: absolute; top: 10px; right: 10px; border: 1px solid #b9c8e8; border-radius: 8px; padding: 7px 10px; color: #172033; background: #fff; font: inherit; font-size: 13px; font-weight: 700; cursor: pointer; }}
    details pre {{ max-width: 100%; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; background: #111827; color: #edf2f7; padding: 16px; border-radius: 8px; overflow: auto; }}
    @media (max-width: 860px) {{ .grid, .band {{ grid-template-columns: 1fr 1fr; }} .safety-list li {{ grid-template-columns: 1fr; }} main {{ padding: 16px; }} h1 {{ font-size: 28px; }} }}
    @media (max-width: 560px) {{
      body {{ font-size: 14px; }} main {{ padding: 12px; }} .hero, section {{ padding: 14px; }} .grid, .band {{ grid-template-columns: 1fr; }}
      .markdown-table {{ overflow: visible; }} .markdown-table table, .markdown-table thead, .markdown-table tbody, .markdown-table tr, .markdown-table th, .markdown-table td {{ display: block; width: 100%; }}
      .markdown-table thead {{ display: none; }} .markdown-table tr {{ border: 1px solid #d9e1ec; border-radius: 8px; margin: 10px 0; overflow: hidden; }}
      .markdown-table td {{ display: grid; grid-template-columns: 86px minmax(0, 1fr); gap: 8px; border: 0; border-bottom: 1px solid #e5ebf3; }}
      .markdown-table td:last-child {{ border-bottom: 0; }} .markdown-table td::before {{ content: attr(data-label); color: #61708a; font-weight: 700; }}
    }}
  </style>
</head>
<body>
<main>
  <div class="hero">
    <h1>AI 测试官报告</h1>
    <p>{html.escape(record.summary)}</p>
    <a class="launcher-link" href="dashboard/">体验模拟 TAPD / 工蜂测试任务 →</a>
    <div class="grid">
      <div class="metric"><b>结论</b><span class="badge {verdict_class}">{html.escape(record.verdict)}</span></div>
      <div class="metric"><b>风险</b>{html.escape(record.risk)}</div>
      <div class="metric"><b>失败分类</b>{html.escape(record.failure_category)}</div>
      <div class="metric"><b>临时测试</b>{temp_test_label}</div>
      <div class="metric"><b>关键工具</b>{required_label}</div>
      <div class="metric"><b>命令</b>共 {len(record.commands)} 条 / 失败 {command_failures} 条</div>
    </div>
  </div>
  <div class="band">
    <section>
      <h2>决策摘要</h2>
      <ul class="compact-list">
        <li>失败分类: <code>{html.escape(record.failure_category)}</code></li>
        <li>{html.escape(recommended)}</li>
        <li>{html.escape(audience)}</li>
      </ul>
    </section>
    <section>
      <h2>Agent 过程证明</h2>
      <ul class="compact-list">
        <li>关键工具检查: <code>{str(record.required_tool_check.passed).lower()}</code></li>
        <li>工具调用: <code>{len(record.agent_turns)}</code></li>
        <li>生成临时测试: <code>{len(record.generated_files)}</code></li>
      </ul>
    </section>
  </div>
  {agent_decision}
  <section>
    <h2>变更意图</h2>
    <p>{html.escape(record.change_intent)}</p>
  </section>
  <div class="band">
    <section><h2>主要风险</h2><ul>{risk_items}</ul></section>
    <section><h2>策略取舍</h2><ul>{strategy_items}</ul></section>
  </div>
  <div class="band">
    <section><h2>已覆盖范围</h2><ul>{coverage_items}</ul></section>
    <section><h2>未覆盖范围</h2><ul>{untested_items}</ul></section>
  </div>
  <section><h2>建议动作</h2><ul>{recommendation_items}</ul></section>
  <section>
    <h2>上下文</h2>
    <ul>
      <li>运行 ID: <code>{html.escape(record.run_id)}</code></li>
      <li>Git 范围: <code>{html.escape(record.git_range)}</code></li>
      <li>代码准备: <code>{html.escape(record.checkout_strategy)}</code> / <code>{html.escape(record.checkout_status)}</code></li>
      <li>代码准备错误: <code>{html.escape(record.checkout_error or "无")}</code></li>
      <li>Skill 已加载: <code>{str(record.skill_used).lower()}</code></li>
      <li>MCP 服务: <code>{html.escape(", ".join(record.mcp_servers) if record.mcp_servers else "无")}</code></li>
    </ul>
  </section>
  <section>
    <h2>关键发现</h2>
    <ul>{findings}</ul>
  </section>
  <section>
    <h2>变更文件 / 风险地图</h2>
    <ul>{changed}</ul>
  </section>
  <section>
    <h2>Agent 生成的临时测试</h2>
    <ul>{generated}</ul>
  </section>
  <section>
    <h2>记忆压缩</h2>
    <ul>
      <li>模式: <code>{html.escape(record.memory_summary.mode)}</code></li>
      <li>状态: <code>{html.escape(record.memory_summary.status)}</code></li>
      <li>原始字符数: <code>{record.memory_summary.source_chars}</code></li>
      <li>摘要字符数: <code>{record.memory_summary.summary_chars}</code></li>
      <li>压缩比例: <code>{record.memory_summary.compression_ratio}</code></li>
      <li>摘要路径: <code>{html.escape(_relative_or_raw(record, record.memory_summary.summary_path))}</code></li>
      <li>关键工具检查: <code>{str(record.required_tool_check.passed).lower()}</code></li>
    </ul>
  </section>
  <section>
    <h2>安全边界</h2>
    {sandbox}
    <ul class="safety-list">{safety}</ul>
  </section>
  <section>
    <h2>执行结果</h2>
    <ul class="commands">{commands}</ul>
  </section>
  <section class="evidence">
    <h2>证据</h2>
    {evidence}
  </section>
  <details>
    <summary>完整 Markdown 报告（已脱敏）</summary>
    <pre>{html.escape(sanitized_markdown)}</pre>
  </details>
</main>
<div class="evidence-modal" id="evidence-modal" hidden role="dialog" aria-modal="true" aria-label="截图原图">
  <div class="evidence-modal-content">
    <button class="evidence-modal-close" type="button" aria-label="关闭原图">关闭 ×</button>
    <img id="evidence-modal-image" alt="">
    <p id="evidence-modal-caption"></p>
  </div>
</div>
<script>
  (() => {{
    const modal = document.getElementById("evidence-modal");
    const image = document.getElementById("evidence-modal-image");
    const caption = document.getElementById("evidence-modal-caption");
    const close = () => {{ modal.hidden = true; image.removeAttribute("src"); }};
    document.querySelectorAll(".evidence-trigger").forEach((trigger) => {{
      trigger.addEventListener("click", () => {{
        image.src = trigger.dataset.imageSrc;
        image.alt = trigger.dataset.imageCaption;
        caption.textContent = trigger.dataset.imageCaption;
        modal.hidden = false;
      }});
    }});
    modal.addEventListener("click", (event) => {{ if (event.target === modal) close(); }});
    modal.querySelector(".evidence-modal-close").addEventListener("click", close);
    document.addEventListener("keydown", (event) => {{ if (event.key === "Escape" && !modal.hidden) close(); }});
  }})();
</script>
</body>
</html>
"""


def _html_evidence(record: RunRecord) -> str:
    if not record.evidence_files:
        return "<p>未捕获截图或证据文件。</p>"
    cards = []
    for item in record.evidence_files:
        try:
            rel = item.relative_to(record.run_dir)
        except ValueError:
            rel = item
        label = html.escape(str(rel))
        src = html.escape(str(rel))
        if item.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            cards.append(
                f"<div><button class=\"evidence-trigger\" type=\"button\" data-image-src=\"{src}\" "
                f"data-image-caption=\"{label}\"><img src=\"{src}\" alt=\"{label}\"></button>"
                f"<p><code>{label}</code></p><p class=\"muted\">点击查看原图；可按 Esc 或关闭按钮返回</p></div>"
            )
        else:
            cards.append(f"<div><p><a href=\"{src}\" target=\"_blank\" rel=\"noopener\"><code>{label}</code></a></p></div>")
    return f"<div class=\"evidence-grid\">{''.join(cards)}</div>"


def _html_required_tools(record: RunRecord) -> str:
    if not record.required_tool_check.required:
        return "<li>无关键工具要求</li>"
    observed = set(record.required_tool_check.observed)
    items = []
    for tool in record.required_tool_check.required:
        status = "已完成" if tool in observed else "缺失"
        css = "" if tool in observed else " class=\"missing\""
        items.append(f"<li{css}><code>{html.escape(tool)}</code> {status}</li>")
    return "".join(items)


def _html_agent_decision(record: RunRecord) -> str:
    if not record.agent_final_output.strip():
        return ""
    text = _render_safe_markdown(
        _sanitize_markdown_for_html(record, redact_secrets(record.agent_final_output.strip()))
    )
    return f"""<section>
    <h2>Agent 判断</h2>
    <div class="agent-decision">{text}</div>
  </section>"""


def _render_safe_markdown(markdown: str) -> str:
    """Render a small, presentation-friendly Markdown subset without trusting HTML."""
    blocks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    list_tag = "ul"
    table_rows: list[list[str]] = []
    code_lines: list[str] = []
    in_code_block = False

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{'<br>'.join(_render_inline_markdown(line) for line in paragraph)}</p>")
            paragraph.clear()

    def flush_list() -> None:
        if list_items:
            blocks.append(f"<{list_tag}>" + "".join(f"<li>{item}</li>" for item in list_items) + f"</{list_tag}>")
            list_items.clear()

    def flush_table() -> None:
        if not table_rows:
            return
        rows = table_rows[:]
        table_rows.clear()
        separator_index = next((index for index, row in enumerate(rows) if _is_table_separator(row)), None)
        header = rows[0]
        body = rows[separator_index + 1 :] if separator_index is not None else rows[1:]
        header_html = "".join(f"<th>{_render_inline_markdown(cell)}</th>" for cell in header)
        body_html = "".join(
            "<tr>"
            + "".join(
                f'<td data-label="{html.escape(header[index] if index < len(header) else "")}">'
                f"{_render_inline_markdown(cell)}</td>"
                for index, cell in enumerate(row)
            )
            + "</tr>"
            for row in body
        )
        blocks.append(f'<div class="markdown-table"><table><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table></div>')

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            flush_paragraph()
            flush_list()
            if in_code_block:
                blocks.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines.clear()
            in_code_block = not in_code_block
            continue
        if in_code_block:
            code_lines.append(raw_line)
            continue
        if _is_markdown_table_row(line):
            flush_paragraph()
            flush_list()
            table_rows.append(_table_cells(line))
            continue
        flush_table()
        if not line.strip():
            flush_paragraph()
            flush_list()
            continue
        heading = re.fullmatch(r"#{1,4}\s+(.+)", line)
        if heading:
            flush_paragraph()
            flush_list()
            level = min(len(line) - len(line.lstrip("#")), 4)
            blocks.append(f"<h{level}>{_render_inline_markdown(heading.group(1))}</h{level}>")
            continue
        quote = re.fullmatch(r">\s?(.+)", line)
        if quote:
            flush_paragraph()
            flush_list()
            blocks.append(f"<blockquote>{_render_inline_markdown(quote.group(1))}</blockquote>")
            continue
        if re.fullmatch(r"\s*(-{3,}|\*{3,}|_{3,})\s*", line):
            flush_paragraph()
            flush_list()
            blocks.append("<hr>")
            continue
        bullet = re.fullmatch(r"[-*+]\s+(.+)", line)
        ordered = re.fullmatch(r"\d+[.)]\s+(.+)", line)
        if bullet or ordered:
            flush_paragraph()
            next_tag = "ol" if ordered else "ul"
            if list_items and list_tag != next_tag:
                flush_list()
            list_tag = next_tag
            list_items.append(_render_inline_markdown((bullet or ordered).group(1)))
            continue
        flush_list()
        paragraph.append(line)

    if in_code_block:
        blocks.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    flush_paragraph()
    flush_list()
    flush_table()
    return "".join(blocks)


def _render_inline_markdown(text: str) -> str:
    rendered: list[str] = []
    for part in re.split(r"(`[^`]+`)", text):
        if part.startswith("`") and part.endswith("`"):
            rendered.append(f"<code>{html.escape(part[1:-1])}</code>")
        else:
            rendered.append(_render_emphasis(html.escape(part)))
    return "".join(rendered)


def _render_emphasis(text: str) -> str:
    text = re.sub(
        r"\*\*([^*]+)\*\*|__([^_]+)__",
        lambda match: f"<strong>{match.group(1) or match.group(2)}</strong>",
        text,
    )
    return re.sub(
        r"(?<!\*)\*([^*]+)\*(?!\*)|(?<!_)_([^_]+)_(?!_)",
        lambda match: f"<em>{match.group(1) or match.group(2)}</em>",
        text,
    )


def _is_markdown_table_row(line: str) -> bool:
    return line.count("|") >= 2 and line.strip().startswith("|")


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_table_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _html_sandbox(record: RunRecord) -> str:
    temp_write_scope = "仅允许测试和证据路径" if record.allow_temp_test_code else "未启用临时写入"
    blocked_count = sum(1 for item in record.safety_checks if item.status == "blocked")
    blocked_text = f"已记录 {blocked_count} 次阻断" if blocked_count else "策略启用，未观察到违规请求"
    return (
        "<div class=\"sandbox-grid\">"
        "<div class=\"sandbox-card\"><b>原始仓库</b><span>只读；不会 commit、push、merge、reset 或评论 MR。</span></div>"
        f"<div class=\"sandbox-card\"><b>临时工作区</b><span>测试只在 <code>{html.escape('runs/<run-id>/repo/')}</code> 中执行。</span></div>"
        f"<div class=\"sandbox-card\"><b>临时写入</b><span>{html.escape(temp_write_scope)}，业务实现文件不可改。</span></div>"
        f"<div class=\"sandbox-card\"><b>危险操作</b><span>{html.escape(blocked_text)}；git 写操作、dtools、部署命令会被拦截。</span></div>"
        "</div>"
    )


def _relative_or_raw(record: RunRecord, path: Path | None) -> str:
    if path is None:
        return "无"
    try:
        return str(path.relative_to(record.run_dir))
    except ValueError:
        return str(path)


def _html_text_list(items: list[str]) -> str:
    return "".join(f"<li>{html.escape(item)}</li>" for item in items) or "<li>无</li>"


def _html_findings(record: RunRecord) -> str:
    failures = [command for command in record.commands if command.returncode != 0]
    if not record.commands:
        return "<li>未选出可安全执行的定向测试命令。</li>"
    if not failures:
        return "<li>未观察到失败的定向测试命令。</li>"
    return "".join(
        "<li>"
        f"<code>{html.escape(item.command)}</code> 失败，分类为 "
        f"<code>{html.escape(classify_command_failure(item)[0])}</code>: "
        f"{html.escape(_failure_excerpt(item))}"
        "</li>"
        for item in failures[:5]
    )


def _html_generated_files(record: RunRecord) -> str:
    if not record.generated_files:
        return "<li>无</li>"
    return "".join(
        "<li>"
        f"<code>{html.escape(_relative_or_raw(record, item.path))}</code>: "
        f"{html.escape(item.reason)}"
        "</li>"
        for item in record.generated_files
    )


def _html_recommended_action(record: RunRecord) -> str:
    if record.verdict == "pass":
        return "定向验证已通过；对外分享前请复核报告证据。"
    if record.failure_category in {"dependency-missing", "environment-missing", "checkout-blocked"}:
        return "验证被环境或依赖阻塞；判断业务风险前需要先补齐运行条件。"
    if record.failure_category == "agent-incomplete":
        return "Agent 严格闭环未完成；请修复模型或工具配置后重跑。"
    if record.verdict == "fail":
        return "在失败命令被解释清楚前，应按阻塞级回归候选处理。"
    return "需要继续跟进；请检查变更文件并补充聚焦验证命令。"


def _audience_context(record: RunRecord) -> str:
    if record.mr_url:
        return f"来源: {record.mr_project}!{record.mr_iid}"
    return "来源: 本地 Git 范围"


def _sanitize_markdown_for_html(record: RunRecord, markdown: str) -> str:
    sanitized = markdown
    replacements = {
        str(record.source_repo): "<source-repo>",
        str(record.workspace_repo): "<isolated-workspace>",
        str(record.run_dir): "<run-dir>",
    }
    for source, replacement in replacements.items():
        sanitized = sanitized.replace(source, replacement)
    return sanitized
