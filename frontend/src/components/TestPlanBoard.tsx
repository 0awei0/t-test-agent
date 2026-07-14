import type { TestPlanItem } from "../types";

interface Props {
  items: TestPlanItem[];
  summary: string;
  structured: boolean;
  selectedId: string;
  onSelect: (item: TestPlanItem) => void;
}

const STATUS_LABELS: Record<TestPlanItem["status"], string> = {
  planned: "待执行",
  running: "执行中",
  passed: "已通过",
  failed: "发现问题",
  blocked: "安全拦截",
};

const LAYER_LABELS: Record<string, string> = {
  unit: "单元测试",
  api: "接口测试",
  browser: "浏览器测试",
  e2e: "端到端测试",
  security: "安全测试",
};

export function TestPlanBoard({ items, summary, structured, selectedId, onSelect }: Props) {
  const finished = items.filter((item) => ["passed", "failed", "blocked"].includes(item.status)).length;
  const adaptive = items.filter((item) => item.adaptive).length;

  return (
    <section className="panel test-plan-board" aria-label="Agent 测试计划">
      <div className="test-plan-heading">
        <div>
          <span className="eyebrow">AGENT TEST PLAN · LIVE</span>
          <h2>Agent 测试计划</h2>
          <p>{summary || "Agent 正在理解需求与变更，测试计划将在形成后逐项展开。"}</p>
        </div>
        <div className="plan-progress" aria-live="polite">
          <strong>{finished}/{items.length || "…"}</strong>
          <span>已完成{adaptive > 0 ? ` · 动态新增 ${adaptive}` : ""}</span>
        </div>
      </div>
      {items.length === 0 ? (
        <div className="plan-waiting"><span className="spinner" />正在生成风险驱动测试计划…</div>
      ) : (
        <ol className="test-plan-flow">
          {items.map((item, index) => (
            <li key={item.id}>
              <button
                type="button"
                className={`plan-node ${item.status} ${selectedId === item.id ? "selected" : ""}`}
                onClick={() => onSelect(item)}
                aria-current={item.status === "running" ? "step" : undefined}
              >
                <span className="plan-node-index">{item.status === "passed" ? "✓" : item.status === "failed" || item.status === "blocked" ? "!" : index + 1}</span>
                <span className="plan-node-body">
                  <span className="plan-node-meta"><b>{LAYER_LABELS[item.layer.toLowerCase()] ?? item.layer}</b>{item.adaptive && <em>Agent 动态新增</em>}<i className={item.status}>{STATUS_LABELS[item.status]}</i></span>
                  <strong>{item.title}</strong>
                  <small>{item.target}</small>
                  {item.detail && <span className="plan-node-detail">{item.detail}</span>}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
      <div className="plan-board-foot">
        <span>{structured ? "来自 Agent 执行前发布的结构化计划" : "根据当前真实命令轨迹实时还原"}</span>
        <span>点击计划项可定位对应命令</span>
      </div>
    </section>
  );
}
