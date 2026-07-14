# AI 测试官比赛最终优化计划（执行中）

## 1. 目标与当前基线

- 比赛方向：方向二「AI 测试官」。
- 截止时间：2026-07-19 23:59:59；内部目标仍为 2026-07-18 前完成提交。
- 当前版本：`main` 已推送至 `origin/main`，代码优化最新提交为 `9fc4c8a Retry unstable competition Agent replays`。
- 当前能力：8 个合成 TAPD 需求与 8 个工蜂 MR 一一对应，每个 MR 均有独立的 `agent-strict` 真实运行脱敏回放。
- 当前验证：后端 103 项单元测试、前端 4 项 Playwright 比赛 E2E、typecheck、build 和依赖审计全部通过。
- 优化目标：不再扩展平台型功能，集中提高比赛交付可信度、评委观看效率、自动验收覆盖和最终提交完整性。

## 2. 执行原则

1. 本计划已确认，按批次执行并记录验证结果。
2. 确认后严格按批次执行；每批只解决一个核心问题。
3. 每批修改后先运行对应验证，再提交并推送 `origin/main`。
4. 不提交 `.env`、访问参数、Webhook、真实 TAPD/MR、原始日志、截图或完整运行产物。
5. 线上继续使用脱敏静态回放；真实执行只在本地隔离工作区进行。
6. 最终稳定部署完成后只申请一次长期链接重新绑定，开发阶段使用临时预览链接。

## 3. 优先级总览

| 批次 | 优先级 | 目标 | 预计耗时 | 是否阻塞提交 |
| --- | --- | --- | ---: | --- |
| 一 | P0 | 让比赛门禁完整验收 8 个真实 Agent 回放 | 0.5 天 | 是 |
| 二 | P0 | 增加前端回放 Playwright E2E | 0.5～1 天 | 是 |
| 三 | P1 | 增加回放控制与评委快速演示模式 | 0.5～1 天 | 否，但强烈建议 |
| 四 | P1 | 强化真实 Agent、自我修正和安全拦截证据 | 0.5～1 天 | 否，但强烈建议 |
| 五 | P0 | 统一文档、部署信息和比赛材料 | 0.5 天 | 是 |
| 六 | P0 | 最终彩排、部署、视频与官网提交 | 0.5～1 天 | 是 |

总预计：3～4 个工作日，其中代码工作约 2～3 天，交付和录制约 1 天。

## 4. 批次一：升级 8 回放比赛发布门禁

### 目标

让 `scripts/competition_check.sh` 验收评委真正看到的 8 个 MR 回放包，而不是只验证旧的单个 `release-guard` 静态包。

### 预计修改

- `scripts/competition_check.sh`
- `scripts/build_mr_replays.py`
- `agents-sdk-agent/src/ai_test_officer/demo/replay_catalog.py`
- `agents-sdk-agent/src/ai_test_officer/release_gate.py` 或新增专用 catalog gate
- 对应 Python 单元测试
- 必要的 README/比赛展示说明

### 工作项

- [x] 在独立临时目录生成或复用 8 个任务回放并导出 dashboard 静态包。
- [x] 强制 manifest 恰好包含 8 个唯一 `task_id`，且 TAPD、MR、回放目录一一对应。
- [x] 校验默认复杂案例为 `task-45`。
- [x] 校验每个任务的实际 verdict/risk 与回放规格一致。
- [x] 校验每个任务通过 `agent-strict` 工具契约，而不是 deterministic 结果冒充 Agent 运行。
- [x] 校验复杂案例包含规划、工具调用、命令、失败日志、证据、隔离和上下文摘要事件。
- [x] 对全部 8 个公开回放执行敏感字段、本地绝对路径、完整日志和完整 `run.json` 扫描。
- [x] 默认比赛门禁重新运行 Agent；仅显式复用模式使用本地已验证回放。
- [x] 输出逐任务简洁汇总和最终 `READY competition package`。

### 验收标准

```bash
scripts/competition_check.sh
```

必须同时满足：

- 102 项单元测试通过。
- 8 个任务全部存在且一一对应。
- 每个任务的预期结论、Agent 工具契约和公开包安全检查通过。
- 任意删除一个回放、篡改结论或注入敏感路径时，门禁返回非零退出码。

### 预期提交

```text
Validate the complete competition replay package
```

## 5. 批次二：增加前端回放 E2E

### 目标

用浏览器自动化保护比赛现场最关键的交互，避免任务映射、静态路径、播放完成或移动端布局在最终部署前发生回归。

### 预计修改

- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/playwright.config.ts`
- `frontend/e2e/competition-replay.spec.ts`
- `scripts/competition_check.sh`
- 必要的稳定选择器或无障碍属性

### 最小用例

- [x] 首页显示 8 张任务卡，且每张卡只有一个 TAPD 和一个 MR。
- [x] 选择不同任务时，测试计划、风险、回放指标和 URL 同步变化。
- [x] `task-45` 能播放到最终结论，并出现工具、策略、命令、证据、上下文摘要和隔离区域。
- [x] 一个通过案例显示 `pass/low`，一个阻断案例显示 `fail/high`。
- [x] 静态部署路径下刷新回放页仍能加载对应资源。
- [x] 回放页增加 Agent 测试计划执行板，并与真实命令状态和定位交互联动。
- [x] 390px 移动端视口无横向溢出，主要操作和发布结论可见。
- [x] 将 E2E 纳入 `competition_check.sh`。

### 验收标准

```bash
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend run e2e
```

### 预期提交

```text
Add competition replay browser coverage
```

## 6. 批次三：优化动态回放控制

### 目标

让评委既能看到真实事件逐步发生，也能在有限时间内快速到达关键决策，不必等待固定延迟播放完整个复杂案例。

### 预计修改

- `frontend/src/api.ts`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- 前端 E2E

### 工作项

- [x] 增加暂停/继续、重新播放、1×/2×速度和“跳到结论”。
- [x] 展示当前事件序号、总事件数和播放状态。
- [x] 提供“一键评委演示”：默认进入 `task-45`，以 2×播放关键过程。
- [x] 保留 `prefers-reduced-motion` 支持。
- [x] 移动端压缩布局，优先展示风险、失败和结论。
- [x] 实时 SSE 模式不伪装为可回退录像；控制器只作用于静态回放。

### 验收标准

- 暂停后事件数量不再增长，继续后从原位置播放。
- 2×播放明显缩短时长，但事件顺序不变。
- 跳到结论后 verdict、失败证据和报告入口均正确。
- 相关 E2E 和前端构建通过。

### 预期提交

```text
Add judge-friendly replay controls
```

## 7. 批次四：强化 Agent 真实性与安全证据

### 目标

减少“预制动画”的观感，并通过真实事件证明 Agent 会自我修正、安全策略会实际阻断危险动作。

### 工作项 A：运行来源卡片

- [x] 展示运行模式、run ID、执行时间和是否通过严格工具检查。
- [x] 展示实际工具调用数、命令数、生成测试数和证据数。
- [x] 明确区分模型自主工具调用与系统确定性安全兜底。

### 工作项 B：自我修正链路

- [x] 将“测试失败 → 读取日志 → 补充隔离边界测试 → 继续验证”标记为失败驱动补测。
- [x] 保留失败轨迹，最终统计继续使用最新有效结果。
- [x] 在复杂案例中提供可直接定位的自适应补测证据。

### 工作项 C：实际安全拦截

- [x] 在合成场景中安全模拟一次远端写请求。
- [x] 由现有安全工具真实拒绝该动作，并生成 `safety_check/blocked` 事件。
- [x] 前端展示请求和拒绝原因。
- [x] 不实际执行危险命令，不访问真实业务资源。

### 工作项 D：准确描述上下文能力

- [x] 将当前“上下文记忆压缩”改为“运行上下文摘要 / 归档压缩”。
- [x] 明确当前摘要在运行后形成，原始 diff、日志和证据可按需回读。
- [x] 本轮不宣称已实现运行中 context-window 压缩恢复。

### 验收标准

- 默认复杂案例能看到运行来源和完整自我修正链。
- 安全案例中存在由真实守卫产生的 blocked 事件。
- 页面和提交文案不存在对“实时执行”或“运行中记忆压缩”的夸大表述。
- Python 测试、前端 E2E 和比赛门禁通过。

### 预期提交

```text
Strengthen Agent provenance and safety evidence
```

## 8. 批次五：统一文档与提交信息

### 目标

清除旧项目名、旧测试数量、旧部署状态和互相冲突的链接策略，使评委材料与当前代码完全一致。

### 预计修改

- `README.md`
- `plans/competition-optimization-plan.md`
- `docs/比赛展示说明.md`
- `docs/复现说明.md`
- `docs/部署.md`
- `docs/作品提交材料.md`

### 工作项

- [x] 统一 EdgeOne 项目名称和 project slug。
- [x] 更新为当前 102 项 Python 测试和 4 项浏览器 E2E 的真实结果。
- [x] 更新 Git 已推送、8 回放已完成和当前部署状态。
- [x] 明确开发阶段使用临时链接，最终稳定部署后再绑定长期链接。
- [x] 更新 3 分钟主演示脚本，使其匹配新的回放控制、来源卡片和安全证据。
- [x] 保证文档不包含临时预览 token、内部链接或本地绝对路径。

### 验收标准

```bash
rg -n "85 个测试|尚未.*推送|ai-test-officer-release-guard|ai-test-officer-promotion-chain" README.md plans docs
git diff --check
```

旧状态搜索结果应为零，或只出现在明确标注的历史记录中。

### 预期提交

```text
Align competition delivery documentation
```

## 9. 批次六：最终彩排、部署与提交

### 目标

形成可提交、可复核、可兜底的最终作品版本。

### 执行清单

- [x] 从干净 `main` 重新运行 8 个 Agent 案例；不稳定结果自动重试后全部合同通过。
- [ ] 连续两次完成 3 分钟主演示，不依赖临时调试操作。
- [x] 生成最终 EdgeOne 静态包并部署到现有项目，部署 ID：`dpfaezfjw7qt`。
- [x] 使用桌面、390px 移动端和无痕窗口检查首页、8 个回放、证据和报告链接。
- [ ] 确认最终部署后，再申请长期链接重新绑定；绑定前继续使用临时链接。
- [x] 生成 123 秒、1920×1080 主演示草稿；提交前建议人工补充讲解或字幕。
- [x] 导出 27 秒兜底视频。
- [x] 准备 1600×900 封面，确保无真实业务和隐私信息。
- [ ] 在比赛官网填写标题、简介、封面、视频和最终链接。
- [ ] 提交后使用无痕窗口再次核验。

### 最终放行条件

```text
PASS clean checkout
PASS 8 Agent replay contracts
PASS frontend E2E and mobile viewport
PASS public export safety
PASS EdgeOne incognito rehearsal
PASS video and cover review
READY official submission
```

## 10. 明确暂缓项

以下能力本次比赛提交前不进入主线：

- 真实 TAPD、工蜂的在线强依赖接入。
- 云端任意仓库和任意命令执行。
- 自动评论、提交、推送、合并或发布真实业务仓库。
- 完整多租户测试工作台。
- 新增更多普通 MR 案例。
- 真正的运行中 context-window 压缩与恢复。
- 大规模视觉重构。

如主线提前完成，可补充一份脱敏的真实适配器证明，但不得让现场演示依赖内网和账号状态。

## 11. 已确认决策

以下范围已确认并执行：

1. 同意先完成批次一、二两个 P0 代码门禁，再做交互增强。
2. 同意批次三只实现 `暂停/继续 + 1×/2× + 跳到结论`，不建设复杂时间轴编辑器。
3. 同意批次四采用真实安全守卫的合成拦截，不接触真实业务环境。
4. 同意将“上下文记忆压缩”准确改名为“运行上下文摘要 / 归档压缩”，本次不实现高风险的运行中压缩恢复。
5. 同意真实 TAPD/工蜂在线接入和平台型能力暂缓。
6. 同意最终部署完成后再统一处理长期链接绑定。

批次一至五已完成；下一步执行批次六的最终部署和彩排。
