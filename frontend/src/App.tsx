import { useEffect, useMemo, useRef, useState } from "react";
import { openStream, isStaticReplay, reportUrl } from "./api";
import type {
  AppEvent,
  CommandEvent,
  EvidenceEvent,
  PhaseName,
  VerdictEvent,
} from "./types";
import { PhaseStepper } from "./components/PhaseStepper";
import { VerdictHero } from "./components/VerdictHero";
import { CommandList } from "./components/CommandList";
import { EvidenceGrid } from "./components/EvidenceGrid";
import { FailureBanner } from "./components/FailureBanner";

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

const SIMULATED_TAPD_CASES = [
  {
    id: "story-promotion",
    tapd: "TAPD #114514 · 大促优惠与库存策略调整",
  },
  {
    id: "story-pricing",
    tapd: "TAPD #114515 · 合作方优惠上限变更",
  },
  {
    id: "story-refund",
    tapd: "TAPD #114516 · 退款角色与订单状态校验",
  },
] as const;

const SIMULATED_MR_CASES = [
  { id: "mr-42", iid: "!42", title: "移除 request_id 幂等保护", summary: "支付重试会重复扣库存", expected: "block", scenario: "promotion-chain" },
  { id: "mr-43", iid: "!43", title: "优惠上限调整与契约同步", summary: "策略与边界测试保持一致", expected: "pass", scenario: "promotion-chain-pass" },
  { id: "mr-44", iid: "!44", title: "库存预占重复扣减", summary: "相同订单重试导致库存归零", expected: "block", scenario: "promotion-chain" },
  { id: "mr-45", iid: "!45", title: "优惠券 30% 边界回归", summary: "临界值校验被错误放宽", expected: "block", scenario: "release-guard" },
  { id: "mr-46", iid: "!46", title: "大促优惠策略修复", summary: "合法券与越界券均已覆盖", expected: "pass", scenario: "release-guard-pass" },
  { id: "mr-47", iid: "!47", title: "退款角色校验缺失", summary: "普通用户可触发高权限退款", expected: "block", scenario: "refund-guard" },
  { id: "mr-48", iid: "!48", title: "退款状态机守卫补齐", summary: "已发货订单拒绝退款", expected: "pass", scenario: "refund-guard-pass" },
  { id: "mr-49", iid: "!49", title: "已发货订单允许退款", summary: "状态迁移绕过发布约束", expected: "block", scenario: "refund-guard" },
  { id: "mr-50", iid: "!50", title: "支付重试回归测试补全", summary: "幂等与库存断言均通过", expected: "pass", scenario: "promotion-chain-pass" },
  { id: "mr-51", iid: "!51", title: "库存允许负数", summary: "并发预占后可售库存穿透", expected: "block", scenario: "release-guard" },
  { id: "mr-52", iid: "!52", title: "运营文案与监控字段", summary: "无业务逻辑风险，回归通过", expected: "pass", scenario: "release-guard-pass" },
  { id: "mr-53", iid: "!53", title: "调试令牌写入响应", summary: "敏感字段可能暴露到前端", expected: "block", scenario: "agent-loop" },
  { id: "mr-54", iid: "!54", title: "订单 API 兼容性修复", summary: "旧请求参数仍可正常处理", expected: "pass", scenario: "promotion-chain-pass" },
  { id: "mr-55", iid: "!55", title: "结算页浏览器回归", summary: "下单按钮在异常路径不可用", expected: "block", scenario: "fullstack" },
  { id: "mr-56", iid: "!56", title: "发布前校验收敛", summary: "定向单测与页面验证均通过", expected: "pass", scenario: "release-guard-pass" },
] as const;

const MR_CASES_PER_PAGE = 5;

const SCENARIO_CHECKS: Record<(typeof SIMULATED_MR_CASES)[number]["scenario"], string[]> = {
  "promotion-chain": ["订单幂等单测", "库存与重试 API", "失败日志归因"],
  "promotion-chain-pass": ["订单幂等单测", "库存与重试 API", "修复后回归确认"],
  "release-guard": ["优惠边界单测", "下单 API", "浏览器截图证据"],
  "release-guard-pass": ["优惠边界单测", "下单 API", "修复后浏览器回归"],
  "refund-guard": ["退款角色校验", "订单状态机", "异常路径断言"],
  "refund-guard-pass": ["退款角色校验", "订单状态机", "修复后回归确认"],
  "agent-loop": ["敏感字段扫描", "临时测试隔离", "安全策略校验"],
  "fullstack": ["后端业务单测", "HTTP API", "结算页浏览器验证"],
};

function DemoLauncher() {
  const [tapdId, setTapdId] = useState<(typeof SIMULATED_TAPD_CASES)[number]["id"]>("story-promotion");
  const [mrId, setMrId] = useState<(typeof SIMULATED_MR_CASES)[number]["id"]>("mr-42");
  const [mrPage, setMrPage] = useState(0);
  const [submitted, setSubmitted] = useState(false);
  const [copied, setCopied] = useState(false);
  const selectedTapd = SIMULATED_TAPD_CASES.find((item) => item.id === tapdId) ?? SIMULATED_TAPD_CASES[0];
  const selectedMr = SIMULATED_MR_CASES.find((item) => item.id === mrId) ?? SIMULATED_MR_CASES[0];
  const totalMrPages = Math.ceil(SIMULATED_MR_CASES.length / MR_CASES_PER_PAGE);
  const visibleMrCases = SIMULATED_MR_CASES.slice(mrPage * MR_CASES_PER_PAGE, (mrPage + 1) * MR_CASES_PER_PAGE);
  const blockedMrCount = SIMULATED_MR_CASES.filter((item) => item.expected === "block").length;
  const passedMrCount = SIMULATED_MR_CASES.length - blockedMrCount;
  const liveRunId = `live-${selectedMr.id}`;
  const plannerMode = selectedMr.expected === "pass" ? "agent" : "agent-strict";
  const runCommand = `uv run ai-test-officer demo run --scenario ${selectedMr.scenario} --demo-root runs/live-demos --runs-root runs/live-runs --run-id ${liveRunId} --planner-mode ${plannerMode} --allow-temp-test-code --visualize --dashboard-port 8789 --env .env`;
  const scenarioChecks = SCENARIO_CHECKS[selectedMr.scenario];

  const selectMr = (nextMrId: (typeof SIMULATED_MR_CASES)[number]["id"]) => {
    const index = SIMULATED_MR_CASES.findIndex((item) => item.id === nextMrId);
    setMrId(nextMrId);
    setMrPage(Math.floor(index / MR_CASES_PER_PAGE));
    setSubmitted(false);
    setCopied(false);
  };

  const copyRunCommand = async () => {
    try {
      await navigator.clipboard.writeText(runCommand);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <main className="launcher-shell">
      <header className="launcher-brand"><span>Release Guard</span><small>AI 测试官 · 比赛演示入口</small></header>
      <section className="launcher-hero">
        <span className="eyebrow">SIMULATED WORKFLOW</span>
        <h1>一句需求，完成发布前测试决策</h1>
        <p>从模拟 TAPD 与工蜂 MR 案例库中选择任务，前端演示如何理解变更、规划验证并给出发布建议。</p>
      </section>
      <section className="launcher-grid">
        <form className="launcher-form" onSubmit={(event) => { event.preventDefault(); setSubmitted(true); }}>
          <div className="form-heading"><h2>创建一次测试任务</h2><span>仅模拟数据</span></div>
          <label>模拟 TAPD 需求<select value={tapdId} onChange={(event) => { setTapdId(event.target.value as typeof tapdId); setSubmitted(false); }}>{SIMULATED_TAPD_CASES.map((item) => <option key={item.id} value={item.id}>{item.tapd}</option>)}</select></label>
          <div className="mr-picker"><div className="mr-picker-heading"><b>模拟工蜂 MR</b><span>{SIMULATED_MR_CASES.length} 条案例 · {passedMrCount} 通过 / {blockedMrCount} 阻断 · 第 {mrPage + 1}/{totalMrPages} 页</span></div><div className="mr-case-list">{visibleMrCases.map((item) => <button key={item.id} type="button" className={`mr-case ${item.expected} ${item.id === mrId ? "selected" : ""}`} onClick={() => selectMr(item.id)} aria-pressed={item.id === mrId}><span className="mr-case-top"><b>MR {item.iid}</b><em>{item.expected === "pass" ? "预期通过" : "预期阻断"}</em></span><strong>{item.title}</strong><small>{item.summary}</small></button>)}</div><div className="mr-pagination">{Array.from({ length: totalMrPages }, (_, index) => <button key={index} type="button" className={index === mrPage ? "active" : ""} onClick={() => { setMrPage(index); setSubmitted(false); }}>{index + 1}</button>)}</div></div>
          <div className="selected-case"><b>已选案例</b><span>{selectedTapd.tapd} / MR {selectedMr.iid} · {selectedMr.title}</span></div>
          <button type="submit">模拟生成测试计划</button>
          <p className="form-note">选项均为合成数据；不会请求 TAPD、工蜂或业务仓库，也不会执行远程写操作。</p>
        </form>
        <aside className="launcher-aside"><h2>评委可见闭环</h2><ol><li>理解变更与风险范围</li><li>选择单测 / API / 浏览器验证</li><li>保留失败截图与命令证据</li><li>输出可执行的发布建议</li></ol><div className="safe-chip">安全边界：合成数据 · 隔离工作区 · 脱敏导出</div></aside>
      </section>
      {submitted && <section className="simulation-result" aria-live="polite"><span>已建立真实运行映射</span><h2>{selectedMr.expected === "pass" ? "修复验证：预期通过" : "回归验证：预期阻断"}</h2><p>已选择：{selectedTapd.tapd} / MR {selectedMr.iid} · {selectedMr.title}。此卡片不会跳转到不匹配的静态回放；下方命令会生成该 MR 对应的真实日志、截图和报告。</p><div className="check-strip"><b>本次验证</b>{scenarioChecks.map((check) => <span key={check}>{check}</span>)}</div><div className="command-box"><code className="run-command">{runCommand}</code><button type="button" className="copy-command" onClick={() => { void copyRunCommand(); }}>{copied ? "已复制" : "复制命令"}</button></div><ol className="live-steps"><li>在项目根目录执行命令；浏览器打开 <code>http://127.0.0.1:8789/?run_id={liveRunId}</code> 查看实时过程。</li><li>完成后查看 <code>runs/live-runs/{liveRunId}/report.html</code>、命令日志和截图证据。</li><li>想先查看完整示例，可打开 <a href="../">默认 Release Guard 证据报告</a>。</li></ol></section>}
    </main>
  );
}

export default function App() {
  const runId = useRunId();
  const staticMode = isStaticReplay();
  const [started, setStarted] = useState<Set<PhaseName>>(new Set());
  const [finished, setFinished] = useState<Set<PhaseName>>(new Set());
  const [commands, setCommands] = useState<Record<string, CommandEvent>>({});
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
          <span className="runid">{staticMode ? "真实执行结果回放" : runId}</span>
          <span className={`conn ${connected ? "on" : ""}`}>
            {connected ? (staticMode ? "已脱敏" : done ? "已结束" : "直播中") : "连接中…"}
          </span>
        </div>
      </header>

      {staticMode && (
        <section className="replay-notice">
          <b>真实执行结果回放</b>
          <span>以下阶段、命令、失败信号和证据来自一次已完成的合成测试运行；当前静态页面不会连接真实 TAPD、工蜂或执行测试。</span>
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
