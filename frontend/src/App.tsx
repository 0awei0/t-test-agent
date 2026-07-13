import { useEffect, useMemo, useRef, useState } from "react";
import {
  getExecutionCapability,
  openStream,
  isStaticReplay,
  reportUrl,
  startDemoExecution,
} from "./api";
import type {
  AppEvent,
  CommandEvent,
  EvidenceEvent,
  PhaseName,
  ToolCallEvent,
  VerdictEvent,
} from "./types";
import { PhaseStepper } from "./components/PhaseStepper";
import { VerdictHero } from "./components/VerdictHero";
import { CommandList } from "./components/CommandList";
import { EvidenceGrid } from "./components/EvidenceGrid";
import { FailureBanner } from "./components/FailureBanner";
import { Timeline } from "./components/Timeline";
import { StrategyPanel } from "./components/StrategyPanel";

const PHASE_ORDER: PhaseName[] = [
  "checkout",
  "planning",
  "executing",
  "validating",
  "reporting",
];

const PHASE_LABELS: Record<PhaseName, string> = {
  checkout: "准备隔离工作区",
  planning: "理解变更 / 规划策略",
  executing: "执行验证",
  validating: "校验结果",
  reporting: "生成报告",
};

function useRunId(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get("run_id") ?? "";
}

const DEMO_TASKS = [
  { id: "task-42", tapdId: "TAPD-114514", requirement: "大促订单需保持支付幂等与库存准确", acceptance: ["同一 request_id 只扣减一次库存", "重复请求返回同一订单"], iid: "!42", mrTitle: "移除 request_id 幂等保护", summary: "支付重试可能重复扣减库存", expected: "block", scenario: "promotion-chain", risk: "支付幂等 / 库存超卖", checks: [["单元测试", "OrderService.checkout", "重复请求不重复扣库存"], ["接口测试", "POST /orders", "相同 request_id 返回一致"], ["日志复核", "失败命令日志", "定位幂等分支缺失"]] },
  { id: "task-43", tapdId: "TAPD-114515", requirement: "优惠上限调整后前后端契约必须一致", acceptance: ["合法优惠正常下单", "越界优惠被明确拒绝"], iid: "!43", mrTitle: "优惠上限调整与契约同步", summary: "策略、文案与边界测试同步更新", expected: "pass", scenario: "promotion-chain-pass", risk: "价格策略 / API 契约", checks: [["单元测试", "优惠边界", "上限内通过、越界拒绝"], ["接口测试", "下单 API", "错误码与契约一致"], ["回归验证", "订单主链", "修复后全部通过"]] },
  { id: "task-45", tapdId: "TAPD-114516", requirement: "大促优惠不得突破 30% 发布红线", acceptance: ["31% 及以上优惠被拒绝", "页面展示与服务端策略一致"], iid: "!45", mrTitle: "优惠券 30% 边界被放宽", summary: "默认 45% 优惠可能直接形成资损", expected: "block", scenario: "release-guard", risk: "优惠资损 / 前后端漂移", checks: [["单元测试", "Coupon Policy", "30% 边界精确校验"], ["接口测试", "Checkout API", "越界优惠返回失败"], ["浏览器测试", "结算页", "保留失败截图证据"]] },
  { id: "task-46", tapdId: "TAPD-114517", requirement: "修复大促订单安全护栏并完成发布回归", acceptance: ["优惠、库存、幂等保护恢复", "浏览器主路径验证通过"], iid: "!46", mrTitle: "大促订单安全护栏修复", summary: "恢复策略检查并补齐回归证据", expected: "pass", scenario: "release-guard-pass", risk: "发布回归 / 防复发", checks: [["单元测试", "订单安全护栏", "核心边界全部通过"], ["接口测试", "下单 API", "契约恢复"], ["浏览器测试", "结算页", "修复后页面回归"]] },
  { id: "task-47", tapdId: "TAPD-114518", requirement: "退款操作必须校验角色与订单状态", acceptance: ["普通用户不能高权限退款", "已发货订单拒绝退款"], iid: "!47", mrTitle: "退款角色校验缺失", summary: "权限与状态机均可能被绕过", expected: "block", scenario: "refund-guard", risk: "越权退款 / 状态机", checks: [["权限测试", "refund role", "普通用户被拒绝"], ["状态机测试", "shipped order", "已发货不可退款"], ["异常路径", "退款接口", "保留失败归因"]] },
  { id: "task-48", tapdId: "TAPD-114519", requirement: "补齐退款权限与状态机守卫", acceptance: ["角色检查恢复", "非法状态迁移被阻止"], iid: "!48", mrTitle: "退款状态机守卫补齐", summary: "权限与订单状态校验完成修复", expected: "pass", scenario: "refund-guard-pass", risk: "退款回归 / 权限边界", checks: [["权限测试", "refund role", "角色矩阵通过"], ["状态机测试", "order state", "非法迁移被拒绝"], ["回归验证", "退款主链", "合法退款仍可用"]] },
  { id: "task-53", tapdId: "TAPD-114520", requirement: "调试能力不得向前端泄露敏感字段", acceptance: ["响应不包含令牌", "临时测试只写隔离目录"], iid: "!53", mrTitle: "调试令牌写入响应", summary: "敏感字段可能暴露到浏览器", expected: "block", scenario: "agent-loop", risk: "敏感信息泄露", checks: [["内容扫描", "HTTP response", "不存在 token 字段"], ["边界测试", "debug endpoint", "生产响应脱敏"], ["安全校验", "临时写入", "仅限隔离测试目录"]] },
  { id: "task-55", tapdId: "TAPD-114521", requirement: "结算页异常路径必须阻止错误下单", acceptance: ["异常优惠不能提交", "失败状态给出明确反馈"], iid: "!55", mrTitle: "结算页异常路径失效", summary: "下单按钮在失败条件下仍可点击", expected: "block", scenario: "fullstack", risk: "页面主链 / 错误下单", checks: [["业务单测", "checkout service", "异常输入被拒绝"], ["接口测试", "checkout API", "失败响应正确"], ["浏览器测试", "结算页", "按钮状态与截图证据"]] },
] as const;

function DemoLauncher() {
  const [taskId, setTaskId] = useState<(typeof DEMO_TASKS)[number]["id"]>("task-45");
  const [planReady, setPlanReady] = useState(false);
  const [copied, setCopied] = useState(false);
  const [canExecute, setCanExecute] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");
  const selectedTask = DEMO_TASKS.find((item) => item.id === taskId) ?? DEMO_TASKS[0];
  const liveRunId = `live-${selectedTask.id}`;
  const runCommand = `uv run ai-test-officer demo run --scenario ${selectedTask.scenario} --demo-root runs/live-demos --runs-root runs/live-runs --run-id ${liveRunId} --planner-mode agent-strict --allow-temp-test-code --visualize --dashboard-host 127.0.0.1 --dashboard-port 8789 --env .env`;

  useEffect(() => {
    void getExecutionCapability().then((capability) => setCanExecute(Boolean(capability?.can_execute)));
  }, []);

  const selectTask = (nextTaskId: (typeof DEMO_TASKS)[number]["id"]) => {
    setTaskId(nextTaskId);
    setPlanReady(false);
    setCopied(false);
    setStartError("");
  };

  const copyRunCommand = async () => {
    try {
      await navigator.clipboard.writeText(runCommand);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  const startExecution = async () => {
    if (!canExecute) {
      setStartError("当前是线上脱敏展示页，没有本地执行器。请复制命令在项目根目录启动，或打开本地 Live Server 后点击执行。");
      return;
    }
    setStarting(true);
    setStartError("");
    try {
      const runId = await startDemoExecution(selectedTask.scenario);
      window.location.assign(`?run_id=${encodeURIComponent(runId)}`);
    } catch (error) {
      setStartError(error instanceof Error ? error.message : "启动失败");
      setStarting(false);
    }
  };

  return (
    <main className="launcher-shell">
      <header className="launcher-brand"><span>Release Guard</span><small>AI 测试官 · 比赛演示入口</small></header>
      <section className="launcher-hero compact">
        <div><span className="eyebrow">SYNTHETIC TASK · REAL AGENT RUN</span><h1>需求与变更一一对应，生成计划后立即验证</h1><p>每张任务卡绑定一个 TAPD 需求和一个工蜂 MR；线上动态复盘真实脱敏事件，本地可一键启动 Agent。</p></div>
        <a className="replay-entry" href="?mode=static">观看真实执行动态复盘 →</a>
      </section>
      <section className="task-workbench">
        <div className="task-library"><div className="section-heading"><div><span>01 · 选择任务</span><h2>TAPD × 工蜂 MR</h2></div><em>一一对应 · 合成数据</em></div><div className="task-list">{DEMO_TASKS.map((item) => <button key={item.id} type="button" className={`task-card ${item.expected} ${item.id === taskId ? "selected" : ""}`} onClick={() => selectTask(item.id)} aria-pressed={item.id === taskId}><div className="task-card-head"><span>{item.tapdId}</span><span>MR {item.iid}</span><em>{item.expected === "pass" ? "修复验证" : "风险阻断"}</em></div><strong>{item.requirement}</strong><p>{item.mrTitle}</p><small>{item.summary}</small></button>)}</div></div>
        <div className="plan-builder"><div className="section-heading"><div><span>02 · Agent 规划</span><h2>测试计划</h2></div><em>{planReady ? "计划已生成" : "等待生成"}</em></div>{planReady ? <div className="test-plan"><div className="pair-summary"><div><span>需求</span><b>{selectedTask.tapdId}</b><p>{selectedTask.requirement}</p></div><div><span>变更</span><b>MR {selectedTask.iid}</b><p>{selectedTask.mrTitle}</p></div></div><div className="plan-risk"><span>核心风险</span><strong>{selectedTask.risk}</strong></div><div className="acceptance"><b>验收标准</b>{selectedTask.acceptance.map((item) => <span key={item}>✓ {item}</span>)}</div><table className="plan-table"><thead><tr><th>验证层</th><th>验证目标</th><th>预期证据</th></tr></thead><tbody>{selectedTask.checks.map(([kind, target, goal]) => <tr key={kind}><td>{kind}</td><td>{target}</td><td>{goal}</td></tr>)}</tbody></table><div className="plan-actions"><button type="button" className="execute-button" onClick={() => { void startExecution(); }} disabled={starting}>{starting ? "正在启动 Agent…" : canExecute ? "开始实际执行" : "在本地启动实际执行"}</button><button type="button" className="copy-command" onClick={() => { void copyRunCommand(); }}>{copied ? "命令已复制" : "复制本地命令"}</button></div>{startError && <p className="execution-note error">{startError}</p>}<p className="execution-note">执行后自动进入实时驾驶舱，展示 Agent 阶段、工具调用、测试命令、失败日志、截图与最终结论。</p></div> : <div className="plan-empty"><span>先确认任务映射</span><h3>{selectedTask.tapdId} ↔ MR {selectedTask.iid}</h3><p>Agent 将把需求验收点、代码风险和验证证据整理为可执行计划。</p><button type="button" onClick={() => setPlanReady(true)}>生成测试计划</button></div>}</div>
      </section>
      <section className="workflow-strip"><span><b>1</b>理解需求与 diff</span><span><b>2</b>形成风险策略</span><span><b>3</b>执行单测 / API / 浏览器</span><span><b>4</b>读取日志与证据</span><span><b>5</b>给出发布决策</span></section>
    </main>
  );
}

export default function App() {
  const runId = useRunId();
  const staticMode = isStaticReplay();
  const [started, setStarted] = useState<Set<PhaseName>>(new Set());
  const [finished, setFinished] = useState<Set<PhaseName>>(new Set());
  const [commands, setCommands] = useState<Record<string, CommandEvent>>({});
  const [toolCalls, setToolCalls] = useState<Record<string, ToolCallEvent>>({});
  const [plannerSteps, setPlannerSteps] = useState<string[]>([]);
  const [task, setTask] = useState("");
  const [changedFiles, setChangedFiles] = useState<{ status: string; path: string }[]>([]);
  const [evidence, setEvidence] = useState<EvidenceEvent[]>([]);
  const [verdict, setVerdict] = useState<VerdictEvent | null>(null);
  const [done, setDone] = useState(false);
  const [connected, setConnected] = useState(false);
  const failureRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!runId && !staticMode) return;
    const source = openStream(
      runId,
      (event: AppEvent) => {
        setConnected(true);
        const d = event.data as Record<string, unknown>;
        switch (event.type) {
          case "context":
            setTask(String(d.task ?? ""));
            setChangedFiles(Array.isArray(d.changed_files) ? (d.changed_files as { status: string; path: string }[]) : []);
            break;
          case "phase":
            if (d.status === "start") {
              setStarted((prev) => new Set(prev).add(d.phase as PhaseName));
            } else if (d.status === "done") {
              setFinished((prev) => new Set(prev).add(d.phase as PhaseName));
            }
            break;
          case "command":
            setCommands((prev) => ({ ...prev, [d.id as string]: d as unknown as CommandEvent }));
            break;
          case "tool_call":
            setToolCalls((prev) => ({ ...prev, [d.id as string]: d as unknown as ToolCallEvent }));
            break;
          case "planner":
            setPlannerSteps((prev) => [...prev, String(d.step ?? "")]);
            break;
          case "evidence":
            setEvidence((prev) =>
              prev.some((e) => e.path === (d.path as string))
                ? prev
                : [...prev, d as unknown as EvidenceEvent]
            );
            break;
          case "verdict":
            setVerdict(d as unknown as VerdictEvent);
            break;
          case "done":
            setDone(true);
            break;
          default:
            break;
        }
      },
      () => setDone(true)
    );
    return () => source?.close();
  }, [runId, staticMode]);

  const commandList = useMemo(() => Object.values(commands), [commands]);
  const toolCallList = useMemo(() => Object.values(toolCalls), [toolCalls]);
  const failures = useMemo(
    () => commandList.filter((c) => c.status === "fail" || c.status === "blocked"),
    [commandList]
  );

  useEffect(() => {
    if (failures.length > 0 && failureRef.current) {
      failureRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [failures.length]);

  if (!runId && !staticMode) {
    return <DemoLauncher />;
  }

  const running = !done && !verdict;
  const verificationCount = commandList.filter((command) => command.status === "ok").length;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">Release Guard</span>
          <span className="sub">AI 测试官 · 发布决策驾驶舱</span>
        </div>
        <div className="runmeta">
          <span className="runid">{staticMode ? "真实执行动态复盘" : runId}</span>
          <span className={`conn ${connected ? "on" : ""}`}>
            {connected ? (staticMode ? (done ? "复盘完成" : "动态播放中") : done ? "已结束" : "直播中") : "连接中…"}
          </span>
        </div>
      </header>

      {staticMode && (
        <section className="replay-notice">
          <b>真实执行动态复盘</b>
          <span>系统正按真实事件顺序逐步播放 Agent 的规划、工具调用、命令、失败日志和证据；数据已脱敏，线上页面不持有模型密钥。</span>
        </section>
      )}

      <section className="briefing">
        <div>
          <span className="eyebrow">{staticMode ? "已完成的合成验证" : "本次测试任务"}</span>
          <h1>{task || "正在读取变更与测试任务…"}</h1>
        </div>
        <div className="risk-map">
          <div><strong>{changedFiles.length}</strong><span>变更文件</span></div>
          <div><strong>{verificationCount}/{commandList.length}</strong><span>验证通过</span></div>
          <div><strong>{evidence.length}</strong><span>可复核证据</span></div>
          <div><strong>{failures.length}</strong><span>阻断信号</span></div>
        </div>
        {changedFiles.length > 0 && (
          <div className="change-list">
            {changedFiles.slice(0, 4).map((file) => <span key={file.path}><b>{file.status}</b> {file.path}</span>)}
          </div>
        )}
      </section>

      <PhaseStepper
        order={PHASE_ORDER}
        labels={PHASE_LABELS}
        started={started}
        finished={finished}
      />

      <VerdictHero verdict={verdict} running={running} failures={failures.length} commands={commandList.length} changedFiles={changedFiles.length} evidence={evidence.length} />

      <section className="grid2 execution-grid">
        <div className="panel">
          <h2>Agent 工具调用 {toolCallList.length > 0 && <span className="count">{toolCallList.length}</span>}</h2>
          <Timeline calls={toolCallList} />
        </div>
        <div className="panel">
          <h2>策略形成过程 {plannerSteps.length > 0 && <span className="count">{plannerSteps.length}</span>}</h2>
          <StrategyPanel steps={plannerSteps} />
        </div>
      </section>

      {failures.length > 0 && (
        <div ref={failureRef}>
          <FailureBanner failures={failures} runId={runId} />
        </div>
      )}

      <section className="panel">
        <h2>测试命令执行 {commandList.length > 0 && <span className="count">{commandList.length}</span>}</h2>
        <CommandList commands={commandList} runId={runId} />
      </section>

      <section className="panel">
        <h2>证据 {evidence.length > 0 && <span className="count">{evidence.length}</span>}</h2>
        <EvidenceGrid evidence={evidence} runId={runId} />
      </section>

      <footer className="footer">
        {verdict ? (
          <a className="reportlink" href={reportUrl(runId)} target="_blank" rel="noreferrer">
            查看完整测试报告 →
          </a>
        ) : (
          <span className="muted">agent 正在执行，时间线会实时更新…</span>
        )}
      </footer>
    </div>
  );
}
