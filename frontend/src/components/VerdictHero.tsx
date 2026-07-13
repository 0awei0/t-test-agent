import type { VerdictEvent } from "../types";

interface Props {
  verdict: VerdictEvent | null;
  running: boolean;
  failures: number;
  commands: number;
  changedFiles: number;
  evidence: number;
}

export function VerdictHero({ verdict, running, failures, commands, changedFiles, evidence }: Props) {
  if (verdict) {
    const vclass =
      verdict.verdict === "fail"
        ? "fail"
        : verdict.verdict === "pass"
        ? "pass"
        : "warn";
    return (
      <div className={`hero ${vclass}`}>
        <div className="hero-left">
          <div className="verdict-badge">{verdict.verdict === "pass" ? "建议发布" : verdict.verdict === "fail" ? "建议阻断" : "需要跟进"}</div>
          <div className="risk">风险等级：{verdict.risk}</div>
        </div>
        <div>
          <p className="summary">{verdict.summary}</p>
          <div className="hero-meta">变更 {changedFiles} 项 · 验证 {commands} 项 · 证据 {evidence} 份 · 异常 {failures} 项</div>
        </div>
      </div>
    );
  }

  return (
    <div className="hero running">
      <div className="hero-left">
        <div className="verdict-badge live">执行中</div>
        <div className="risk">已执行命令 {commands} 条 · 失败 {failures} 条</div>
      </div>
      <div>
        <p className="summary">{running ? "Agent 正在理解变更、规划并执行验证…" : "正在连接执行流…"}</p>
        <div className="hero-meta">变更 {changedFiles} 项 · 已验证 {commands} 项 · 已沉淀证据 {evidence} 份</div>
      </div>
    </div>
  );
}
