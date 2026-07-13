# AI 测试官详细执行计划（待确认）

## 1. 审批结论摘要

本计划建议按 7 个批次执行，每个批次保持单一目标，完成对应验证后单独提交并推送 `origin/main`。任何批次验证失败时，不进入下一批次。

推荐决策：

1. `agents-sdk-agent/` 作为唯一活动后端实现。
2. `codex-agent/` 保留精简归档，但不参与安装、CI 和默认文档主线。
3. `release-guard` 作为比赛主演示，`agent-loop` 作为快速兜底，`release-guard-pass` 作为修复对照。
4. EdgeOne Makers 作为最终比赛入口；FUE 仅作内部分享或备用入口。
5. 不把完整 EdgeOne 官方 Skills 源码 vendoring 到产品仓库；保留安装来源/锁定信息和必要部署文档。
6. 不在截止前建设完整 TAPD 平台、线上巡检、入站机器人或云端任意代码执行。

## 2. 执行纪律

- 本计划获确认前，不开始产品代码优化。
- 不覆盖、回滚或清理无法确认归属的现有改动。
- 不使用 `git reset --hard`、`git clean`、强制推送或重写历史。
- 不提交 `.env`、Token、Webhook、真实 MR/TAPD 数据、日志、截图或生成报告。
- 真实业务仓库保持只读；临时测试只写入 `runs/<run-id>/repo/`。
- 每批先检查 diff，再执行验证；验证通过后才提交和推送。
- 每批提交后更新主计划中的完成状态和验证记录。

## 3. 批次零：建立安全基线

### 目标

先消除误提交 2.7 GB `runs/`、前端依赖、core dump、本地日志和秘密文件的风险。

### 预计修改

- `.gitignore`
- `reports/.gitkeep`
- `runs/.gitkeep`
- `plans/competition-optimization-plan.md`
- `plans/phase-1-delivery-cleanup.md`

### 具体动作

- 去除 `.gitignore` 尾随空格和重复 `.env` 规则。
- 增加 `.env.*`，但保留 `.env.example`。
- 明确忽略：
  - `frontend/node_modules/`
  - `frontend/dist/`
  - `.playwright-mcp/`
  - `.fue/`
  - `.edgeone/`
  - `.tef_dist/`
  - `core`、`core.*`
  - `runs/*`、`reports/*`
- 恢复 `reports/.gitkeep`，并为 `runs/` 保留 `.gitkeep`。
- 使用 `git check-ignore -v` 验证所有目标路径。
- 对待提交文件执行秘密与本地绝对路径扫描。

### 不做

- 不删除 `core.1694096` 或 `runs/` 内容，只保证它们不会进入 Git。
- 不处理业务代码。
- 不调整比赛展示逻辑。

### 验收

```bash
git diff --check
git check-ignore -v core.1694096 frontend/node_modules frontend/dist .fue .playwright-mcp
git status --short
```

### 预期提交

```text
Harden local artifact ignore rules
```

## 4. 批次一：完成 Agents SDK 迁移收口

### 目标

形成一个结构自洽的活动实现，并确认旧根目录删除没有遗漏关键能力。

### 预计纳入

- `agents-sdk-agent/`
- `codex-agent/` 的精简归档内容
- `pyproject.toml`
- `uv.lock`
- `.github/workflows/ci.yml`
- `.env.example`
- `.codex/config.toml`
- `config/mcporter.json`
- `scripts/showcase_release_guard.sh`
- `scripts/showcase_agent_loop.sh`

### 预计确认删除

- 根目录旧 `src/ai_test_officer/`
- 根目录旧 `tests/`
- 旧 scenario 生成脚本
- 已迁入归档目录的旧文档
- 已迁入归档目录的示例 diff

### 模块核对

| 旧能力 | Agents SDK 对应实现 | 验证方式 |
| --- | --- | --- |
| CLI | `cli.py` | CLI parser/command tests |
| Agent 执行 | `agent/`、`execution/` | planner/runner tests |
| Demo | `demo/` | demo tests + showcase smoke |
| Doctor | `showcase_doctor.py`、`mcp/smoke.py` | doctor/structure tests |
| Git/MR | `tools/git.py`、`integrations/gongfeng.py` | runner/gongfeng tests |
| Report | `report.py`、`report_site.py` | report tests |
| 可视化 | `events.py`、`live_server.py`、`frontend/` | server tests + frontend build |
| WeCom | `integrations/wecom.py`、`notify.py` | notify tests |

### 重复代码审查

重点判断以下文件是否职责重复，能否在不扩大风险的前提下收敛：

- `git_tools.py` 与 `tools/git.py`
- `runner.py` 与 `execution/runner.py`
- `workspace.py` 与 `execution/workspace.py`
- `agent_summary.py` 与 `agent/summary.py`
- `notify.py` 与 `integrations/wecom.py`

原则：截止前只删除已证明无引用或纯兼容转发的重复层，不进行大规模重构。

### EdgeOne Skills 处理建议

- 不提交 `.codebuddy/settings.local.json`。
- 不提交 `.codebuddy/skills` 链接。
- 不提交完整 `.agents/skills/edgeone-makers-*` 和 `.agents/skills/makers-*` vendored 源码。
- 保留 `skills-lock.json` 或在部署文档记录官方安装来源，二选一后保持一致。
- 仓库只保留项目自有的 `.agents/skills/ai-test-officer/`。

理由：官方 Skills 是开发/部署工具依赖，不是参赛作品运行代码；整包提交会放大仓库噪声和后续更新成本。

### 验收

```bash
uv --version
uv sync --locked --group dev
uv lock --check
uv run ruff check .
uv run python -m unittest discover -s agents-sdk-agent/tests -p 'test_*.py' -v
uv run ai-test-officer --help
npm --prefix frontend ci
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

如受限环境禁止监听端口，需在普通开发环境补跑 `test_live_server.py` 和 `release-guard-pass`，不能把权限失败当作代码通过。

### 预期提交

```text
Complete the Agents SDK migration
```

## 5. 批次二：统一比赛主演示

### 目标

让代码、脚本、Skill 和文档只讲一套现场故事。

### 预计修改

- `README.md`
- `.agents/skills/ai-test-officer/SKILL.md`
- `docs/比赛展示说明.md`
- `docs/复现说明.md`
- `docs/部署.md`
- `scripts/showcase_release_guard.sh`
- `scripts/showcase_agent_loop.sh`
- 必要时调整 `cli.py` 的帮助文本和默认值

### 统一口径

- 主案例：`release-guard`
- 兜底案例：`agent-loop`
- 修复对照：`release-guard-pass`
- 正式模式：`agent-strict`
- 离线排版检查：`deterministic`
- 最终提交：EdgeOne Makers
- 内部分享：FUE
- 在线页面：真实执行结果回放，不宣称在静态站在线运行测试

### 脚本行为

`showcase_release_guard.sh`：

1. 检查 `.env` 和模型配置状态，但不输出值。
2. 运行 `release-guard`。
3. 导出 EdgeOne 静态包。
4. 运行 `demo doctor`。
5. 输出部署目录和下一步命令。

`showcase_agent_loop.sh`：

1. 使用独立 run-id 和输出目录。
2. 快速完成 Agent 工具闭环。
3. 导出备用静态包。
4. 不覆盖主演示产物。

### 验收

- 文档不存在相互冲突的“推荐主案例”。
- 所有复制命令都引用实际存在的 CLI 参数。
- 两个脚本从空 `runs/` 状态均可执行。
- 模型缺失时明确失败或降级，不伪装成 Agent 自主执行。

### 预期提交

```text
Unify the competition showcase flow
```

## 6. 批次三：实现一键比赛发布门禁

### 目标

通过一个命令判断当前版本是否具备提交和现场演示资格。

### 预计新增或修改

- `scripts/competition_check.sh`
- `agents-sdk-agent/tests/` 中必要的发布门禁测试
- `agents-sdk-agent/src/ai_test_officer/showcase_doctor.py`
- 必要时增加结构化校验辅助函数
- README 中增加门禁入口

### 门禁层级

#### 快速静态检查

- uv 版本和 lock。
- Ruff。
- Python 单测。
- 前端 typecheck/build。
- `git diff --check`。

#### 场景语义检查

- `release-guard` 必须输出 `verdict=fail`、`risk=high`。
- `release-guard-pass` 必须输出 `verdict=pass`、`risk=low`。
- `agent-loop` 必须包含：
  - changed file 读取；
  - diff 读取；
  - 临时测试写入；
  - 测试命令执行；
  - 失败日志读取；
  - 最终 Agent 输出。

#### 公开包安全检查

- 不存在完整 `run.json`。
- 不存在 `.env`、Token、Webhook 和密钥字段值。
- 不存在 `/data/workspace/`、`/root/` 等本地绝对路径。
- 不存在原始命令日志。
- 只包含公开报告、`public-run.json`、脱敏事件和必要合成证据。

### 输出

终端输出简洁汇总：

```text
PASS code quality
PASS backend tests
PASS frontend build
PASS release-guard blocked unsafe release
PASS release-guard-pass approved repaired release
PASS agent-loop tool evidence
PASS public export safety
READY competition package
```

任一失败立即返回非零退出码并指出失败阶段与证据路径。

### 预期提交

```text
Add a competition release gate
```

## 7. 批次四：强化报告的决策价值

### 目标

让评委在首页 30 秒内看懂 Agent 的判断依据、测试取舍和发布建议。

### 预计修改

- `models.py`
- `agent/planner.py`
- `memory/run_memory.py`
- `prompts/test_officer.md`
- `prompts/reporter.md`
- `report.py`
- `report_site.py`
- 对应 report、memory、planner 测试

### 结构化字段

优先复用现有 `RunRecord`，必要时增加：

- `change_intent`
- `risk_findings`
- `strategy_rationale`
- `coverage_scope`
- `untested_scope`
- `recommendations`

不把所有内容塞进模型自由文本；关键发布字段应有确定性 fallback。

### 报告首页顺序

1. 发布结论：通过、阻断、补测或环境阻塞。
2. 变更意图。
3. 最高风险及证据。
4. 测试策略与取舍。
5. 实际执行结果。
6. 未覆盖范围。
7. 建议动作。
8. 完整工具轨迹和日志链接。

### Agent 与确定性逻辑区分

- 标记模型主动调用的工具。
- 标记 deterministic planner 选择的命令。
- 标记安全策略阻止的动作。
- 标记环境缺失与业务失败的区别。
- 不把 fallback 结果描述成模型自主判断。

### 验收

- HTML、Markdown、JSON 三种输出语义一致。
- 中英文内容默认中文优先。
- 结论可追溯到命令、日志、截图或临时测试。
- 长输出压缩仍保留开头和结尾证据。
- WeCom 摘要只保留结论、最高风险和详情链接。

### 预期提交

```text
Make test reports decision ready
```

## 8. 批次五：优化在线展示和真实回放

### 目标

减少“只是模拟网页”的观感，同时保持静态站安全、稳定和可部署。

### 预计修改

- `frontend/src/`
- `report_site.py`
- `events.py`
- `docs/比赛展示说明.md`
- 前端测试或构建检查

### 页面设计

- 首屏显示一次脱敏真实执行结果。
- 仪表盘读取同目录 `events.jsonl` 回放真实阶段和工具事件。
- 明确标签：`真实执行结果回放`。
- 模拟 TAPD/MR 选择保留为体验入口，但标记为合成数据。
- 提供复制本地真实执行命令。
- 展示隔离工作区和原始仓库只读边界。
- 手机端优先展示结论、风险和截图，折叠详细工具轨迹。

### 不做

- 不在静态前端保存模型或内部平台凭据。
- 不从浏览器直接调用 TAPD、工蜂或业务仓库。
- 不在 EdgeOne 静态页面执行任意测试命令。

### 验收

```bash
npm --prefix frontend run typecheck
npm --prefix frontend run build
uv run ai-test-officer report export-fue ...
uv run ai-test-officer demo doctor --fue-public ...
```

并在桌面和手机尺寸人工检查首页、回放页、截图和详情链接。

### 预期提交

```text
Improve the competition report replay
```

## 9. 批次六：部署与现场彩排

### 目标

产出可提交链接、演示视频和三档现场方案。

### 执行动作

1. 在干净 checkout 执行 `scripts/competition_check.sh`。
2. 使用真实模型运行 `release-guard` 两次。
3. 使用真实模型运行 `agent-loop` 一次。
4. 确认 Playwright 生成合成截图。
5. 导出并部署 EdgeOne Makers。
6. 使用电脑和手机验证预览链接。
7. 运行 WeCom dry-run；拿到稳定详情链接后再决定是否真实发送。
8. 录制 2～3 分钟主演示视频。
9. 准备作品标题、封面、200 字简介和作品链接。
10. 2026-07-18 前完成官网提交。

### 三档现场方案

- A：3 分钟实时主演示 `release-guard`。
- B：30 秒稳定兜底 `agent-loop`。
- C：模型、浏览器或网络异常时，打开 EdgeOne 真实执行回放。

### 验收

- 主演示连续两次结论一致。
- 截图、日志摘要、事件流和最终报告齐全。
- EdgeOne 页面电脑和手机均可访问。
- 公开包通过 doctor 和人工敏感信息复核。
- 官网作品字段全部填写完成。

### 预期提交

部署说明或提交材料如有代码/文档变化，使用：

```text
Finalize the competition delivery
```

## 10. 批次七：有余量时的真实接入增强

### 进入条件

只有批次零至六全部完成且比赛提交已成功，才进入本批次。

### 最小范围

- TAPD 只读需求摘要。
- 工蜂 MR 只读元数据和 diff。
- 需求验收点与代码变更映射。
- 已覆盖、未覆盖和风险缺口矩阵。
- 所有内容留在本地忽略目录，公开导出仅使用合成或脱敏结果。

### 不做

- 不评论 MR。
- 不修改业务仓库。
- 不提交、推送、合并或部署。
- 不建设长期调度与多租户服务。

## 11. 风险与回退

| 风险 | 预防 | 回退 |
| --- | --- | --- |
| 大规模迁移遗漏旧能力 | 先做模块映射和旧新测试对照 | 保留 `codex-agent/` 精简归档 |
| 模型输出不稳定 | `agent-strict` 关键工具门禁、固定合成场景 | 切换 `agent-loop` 或真实回放 |
| Playwright/Chromium 不可用 | 彩排前安装并做 doctor | 展示已有脱敏截图和 API/单测证据，明确环境阻塞 |
| 本地端口不可监听 | 在普通开发环境补跑 server 测试 | 静态事件回放，不伪造通过 |
| EdgeOne 预览链接失效 | 提前部署并检查有效期 | 更新预览链接或使用备用 FUE |
| 公开包泄密 | 自动 doctor + 文件扫描 + 人工复核 | 阻止部署，重新脱敏导出 |
| 截止前范围膨胀 | P0/P1/P2 严格分层 | 放弃批次七和非必要重构 |

## 12. 需要确认的决策

请确认以下默认方案：

- [ ] 同意 `release-guard` 为主案例，`agent-loop` 为兜底。
- [ ] 同意保留精简 `codex-agent/` 归档，不保留重复运行产物和敏感材料。
- [ ] 同意不提交完整 EdgeOne 官方 Skills 源码，只保留安装/锁定信息和部署文档。
- [ ] 同意每个批次验证通过后单独 commit 并 push 到 `origin/main`。
- [ ] 同意在比赛提交前暂停完整 TAPD、巡检和入站机器人扩展。
- [ ] 同意只有普通开发环境完整通过本地端口和 Playwright 验证后，才把主演示标记为 Ready。

确认后从“批次零：建立安全基线”开始执行。
