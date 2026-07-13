import { useEffect, useMemo, useRef, useState } from "react";
import {
  getExecutionCapability,
  getReplayCatalog,
  openStream,
  isStaticReplay,
  replayUrl,
  reportUrl,
  startDemoExecution,
} from "./api";
import type { PlaybackState, ReplayItem, StreamHandle } from "./api";
import type {
  AppEvent,
  CommandEvent,
  EvidenceEvent,
  IsolationEvent,
  MemoryEvent,
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
  const [copied, setCopied] = useState(false);
  const [canExecute, setCanExecute] = useState(false);
  const [replays, setReplays] = useState<Record<string, ReplayItem>>({});
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");
  const selectedTask = DEMO_TASKS.find((item) => item.id === taskId) ?? DEMO_TASKS[0];
  const selectedReplay = replays[selectedTask.id];
  const liveRunId = `live-${selectedTask.id}`;
  const runCommand = `uv run ai-test-officer demo run --scenario ${selectedTask.scenario} --demo-root runs/live-demos --runs-root runs/live-runs --run-id ${liveRunId} --planner-mode agent-strict --allow-temp-test-code --visualize --dashboard-host 127.0.0.1 --dashboard-port 8789 --env .env`;

  useEffect(() => {
    void getExecutionCapability().then((capability) => setCanExecute(Boolean(capability?.can_execute)));
    void getReplayCatalog().then((catalog) => {
      if (!catalog) return;
      setReplays(Object.fromEntries(catalog.items.map((item) => [item.task_id, item])));
      if (DEMO_TASKS.some((task) => task.id === catalog.default_task_id)) {
        setTaskId(catalog.default_task_id as (typeof DEMO_TASKS)[number]["id"]);
      }
    });
  }, []);

  const selectTask = (nextTaskId: (typeof DEMO_TASKS)[number]["id"]) => {
    setTaskId(nextTaskId);
    setCopied(false);
    setStartError("");
  };

  const replayHref = selectedReplay && canExecute
    ? `?run_id=${encodeURIComponent(selectedReplay.run_id)}`
    : replayUrl(selectedTask.id);

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
        <a className="replay-entry" href={`${replayUrl("task-45")}&judge=1`}>一键评委演示（2×）→</a>
      </section>
      <section className="task-workbench">
        <div className="task-library"><div className="section-heading"><div><span>01 · 选择任务</span><h2>TAPD × 工蜂 MR</h2></div><em>一一对应 · 合成数据</em></div><div className="task-list">{DEMO_TASKS.map((item) => { const replay = replays[item.id]; return <button key={item.id} type="button" className={`task-card ${item.expected} ${item.id === taskId ? "selected" : ""}`} onClick={() => selectTask(item.id)} aria-pressed={item.id === taskId}><div className="task-card-head"><span>{item.tapdId}</span><span>MR {item.iid}</span><em>{replay ? "● 已有真实回放" : item.expected === "pass" ? "修复验证" : "风险阻断"}</em></div><strong>{item.requirement}</strong><p>{item.mrTitle}</p><small>{item.summary}</small>{replay && <span className="replay-metrics">{replay.tool_calls} 次工具调用 · {replay.verdict}/{replay.risk}</span>}</button>; })}</div></div>
        <div className="plan-builder"><div className="section-heading"><div><span>02 · Agent 计划</span><h2>可执行测试计划</h2></div><em>随 MR 即时更新</em></div><div className="test-plan"><div className="pair-summary"><div><span>需求</span><b>{selectedTask.tapdId}</b><p>{selectedTask.requirement}</p></div><div><span>变更</span><b>MR {selectedTask.iid}</b><p>{selectedTask.mrTitle}</p></div></div><div className="plan-risk"><span>核心风险</span><strong>{selectedTask.risk}</strong></div><div className="acceptance"><b>验收标准</b>{selectedTask.acceptance.map((item) => <span key={item}>✓ {item}</span>)}</div><table className="plan-table"><thead><tr><th>验证层</th><th>验证目标</th><th>预期证据</th></tr></thead><tbody>{selectedTask.checks.map(([kind, target, goal]) => <tr key={kind}><td>{kind}</td><td>{target}</td><td>{goal}</td></tr>)}</tbody></table>{selectedReplay && <div className="replay-summary"><strong>真实运行已就绪</strong><span>{selectedReplay.tool_calls} 次工具调用</span><span>{selectedReplay.planner_steps} 个策略事件</span><span>上下文保留 {(selectedReplay.compression_ratio * 100).toFixed(1)}%</span></div>}<div className="plan-actions primary-replay">{selectedReplay ? <a className="execute-button replay-button" href={replayHref}>播放此 MR 真实动态回放</a> : canExecute ? <button type="button" className="execute-button" onClick={() => { void startExecution(); }} disabled={starting}>{starting ? "正在启动 Agent…" : "开始实际执行并生成回放"}</button> : <span className="execute-button replay-button unavailable">该回放尚未生成</span>}{selectedReplay && canExecute ? <button type="button" className="copy-command" onClick={() => { void startExecution(); }} disabled={starting}>{starting ? "正在启动…" : "重新实际执行"}</button> : <button type="button" className="copy-command" onClick={() => { void copyRunCommand(); }}>{copied ? "命令已复制" : "复制本地复跑命令"}</button>}</div>{startError && <p className="execution-note error">{startError}</p>}<p className="execution-note">回放来自该 MR 已完成的真实 Agent 运行；本地工作台还可重新执行并实时观看。</p></div></div>
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
  const [memory, setMemory] = useState<MemoryEvent | null>(null);
  const [isolation, setIsolation] = useState<IsolationEvent | null>(null);
  const [done, setDone] = useState(false);
  const [connected, setConnected] = useState(false);
  const [playback, setPlayback] = useState<PlaybackState>({ current: 0, total: 0, paused: false, speed: 1, finished: false });
  const failureRef = useRef<HTMLDivElement | null>(null);
  const streamRef = useRef<StreamHandle | null>(null);

  useEffect(() => {
    if (!runId && !staticMode) return;
    const resetReplay = () => {
      setStarted(new Set());
      setFinished(new Set());
      setCommands({});
      setToolCalls({});
      setPlannerSteps([]);
      setTask("");
      setChangedFiles([]);
      setEvidence([]);
      setVerdict(null);
      setMemory(null);
      setIsolation(null);
      setDone(false);
      setConnected(false);
    };
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
          case "memory":
            setMemory(d as unknown as MemoryEvent);
            break;
          case "isolation":
            setIsolation(d as unknown as IsolationEvent);
            break;
          case "done":
            setDone(true);
            break;
          default:
            break;
        }
      },
      () => setDone(true),
      resetReplay,
      setPlayback
    );
    streamRef.current = source;
    return () => source?.close();
  }, [runId, staticMode]);

  const commandList = useMemo(() => Object.values(commands), [commands]);
  const effectiveCommandList = useMemo(() => {
    const latest = new Map<string, CommandEvent>();
    for (const command of commandList) latest.set(command.command, command);
    return Array.from(latest.values());
  }, [commandList]);
  const toolCallList = useMemo(() => Object.values(toolCalls), [toolCalls]);
  const failures = useMemo(
    () => effectiveCommandList.filter((c) => c.status === "fail" || c.status === "blocked"),
    [effectiveCommandList]
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
  const verificationCount = effectiveCommandList.filter((command) => command.status === "ok").length;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">Release Guard</span>
          <span className="sub">AI 测试官 · 发布决策驾驶舱</span>
        </div>
        <div className="runmeta">
          {staticMode && <a className="backlink" href="./">← 选择其他 MR</a>}
          <span className="runid">{staticMode ? "真实执行动态复盘" : runId}</span>
          <span className={`conn ${connected ? "on" : ""}`}>
            {connected ? (staticMode ? (done ? "复盘完成" : "动态播放中") : done ? "已结束" : "直播中") : "连接中…"}
          </span>
        </div>
      </header>

      {staticMode && (
        <section className="replay-notice">
          <div><b>真实执行动态复盘</b><span>按真实事件顺序播放 Agent 的规划、工具、命令、失败日志和证据；数据已脱敏。</span></div>
          <div className="replay-controls" aria-label="回放控制">
            <button type="button" onClick={() => playback.paused ? streamRef.current?.resume?.() : streamRef.current?.pause?.()} disabled={playback.finished}>{playback.paused ? "继续" : "暂停"}</button>
            {[1, 2].map((speed) => <button key={speed} type="button" className={playback.speed === speed ? "active" : ""} onClick={() => streamRef.current?.setSpeed?.(speed)}>{speed}×</button>)}
            <button type="button" onClick={() => streamRef.current?.skipToEnd?.()} disabled={playback.finished}>跳到结论</button>
            <button type="button" onClick={() => streamRef.current?.restart?.()}>重新播放</button>
            <span className="replay-progress" aria-live="polite">{playback.current}/{playback.total || "…"}</span>
          </div>
        </section>
      )}

      <section className="briefing">
        <div>
          <span className="eyebrow">{staticMode ? "已完成的合成验证" : "本次测试任务"}</span>
          <h1>{task || "正在读取变更与测试任务…"}</h1>
        </div>
        <div className="risk-map">
          <div><strong>{changedFiles.length}</strong><span>变更文件</span></div>
          <div><strong>{verificationCount}/{effectiveCommandList.length}</strong><span>最终验证通过</span></div>
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

      <section className="grid2 capability-grid">
        <div className="panel capability-panel memory-panel">
          <h2>上下文记忆压缩</h2>
          {memory ? <><strong>{(memory.compression_ratio * 100).toFixed(1)}%</strong><p>{memory.source_chars.toLocaleString()} 字符压缩为 {memory.summary_chars.toLocaleString()} 字符，原始 diff 与日志保留在 {memory.artifact_count} 个隔离证据中，Agent 可按需回读。</p></> : <p className="muted">运行结束时生成结构化记忆摘要…</p>}
        </div>
        <div className="panel capability-panel isolation-panel">
          <h2>安全隔离边界</h2>
          {isolation ? <div className="guardrails"><span>✓ 原仓库只读</span><span>✓ 隔离副本执行</span><span>✓ 测试命令白名单</span><span>✓ 仅测试/证据目录可写</span><span>✓ 禁止远端变更</span></div> : <p className="muted">正在确认隔离工作区与命令策略…</p>}
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
