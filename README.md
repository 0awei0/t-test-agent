# T Test Agent

AI Test Officer MVP for the hackathon direction `AI 测试官`.

This version is rebuilt around the OpenAI Agents SDK. The older Codex SDK
implementation is archived under `codex-agent/` for reference only.

## Project Layout

- `agents-sdk-agent/`: current implementation and tests.
  - `src/ai_test_officer/agent/`: model provider setup, Agents SDK summaries, tool-call smoke tests.
  - `src/ai_test_officer/context/`: MR/diff indexing and structured context summaries.
  - `src/ai_test_officer/prompts/`: Markdown prompts used by Agents SDK components.
  - `src/ai_test_officer/tools/`: safe local tools, read-only git helpers, command/write guards.
  - `src/ai_test_officer/execution/`: isolated run workspace creation, planning, and test execution.
  - `src/ai_test_officer/memory/`: local prompt/context compaction and run-memory shaping.
  - `src/ai_test_officer/skill/`: repo skill instruction loading.
  - `src/ai_test_officer/mcp/`: project MCP configuration loading.
  - `src/ai_test_officer/integrations/`: outbound integrations such as WeCom.
- `codex-agent/`: archived Codex SDK implementation.
- `frontend/`: React + Vite live dashboard and Playwright competition E2E. Built output lands
  in `frontend/dist/` and is served by the live server or bundled into the public replay package.
- `runs/`: local ignored run workspaces, generated test code, logs, evidence, and reports.
- `.codex/`: project MCP configuration template for non-internal tools.
- `config/mcporter.json`: on-demand internal-platform endpoints for `mcporter-internal`.
- `docs/部署.md`: EdgeOne Makers competition deployment and submission guide.
- `docs/复现说明.md`: simulated TAPD/MR cases, local test execution, and export reproduction guide.
- `.agents/`: repo-level skill instructions for Codex users.

## Safety Model

The original business repository is read-only. Each run creates an isolated
workspace under `runs/<run-id>/repo/`, applies the requested git range there,
and writes all generated tests, logs, screenshots, reports, and JSON metadata
under the same `runs/<run-id>/` directory.

The tool layer rejects remote or branch-mutating operations such as `git push`,
`git commit`, `git merge`, `git reset`, deployment commands, and arbitrary shell
commands. Temporary test code is disabled by default and can only be written
inside the isolated run workspace when `--allow-temp-test-code` is passed.

## Setup

```bash
uv sync --locked --group dev
```

Model-backed summaries are optional. Without a model key the runner still clones
the repo, creates temporary tests when allowed, runs local commands, and writes
reports. To use Doubao through the OpenAI-compatible Ark endpoint, put this in
local `.env`:

```bash
ARK_API_KEY=<your-ark-key>
AI_TEST_OFFICER_MODEL=doubao-seed-2-1-turbo-260628
AI_TEST_OFFICER_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
AI_TEST_OFFICER_OPENAI_API=chat_completions
AI_TEST_OFFICER_DISABLE_TRACING=true
```

For WeCom outbound summaries, keep one of these in local `.env`:

```bash
WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<key>
# or
WECOM_WEBHOOK_KEY=<key>
```

For Playwright evidence later:

```bash
uv sync --locked --extra e2e --group dev
uv run python -m playwright install chromium
```

## Usage

## Competition Showcase

比赛现场优先使用 `release-guard` 合成场景：一次大促订单变更会同时触发优惠策略、支付幂等和库存风险，Agent 需要读取 diff、自主规划单测/API/浏览器验证、保留截图证据并给出发布建议。
它不依赖真实业务环境；`agent-loop` 保留为 30 秒稳定兜底，真实 MR 结果仅作为备选材料。

另外提供两个需要 Agent 多轮定位的合成 case：

```bash
# 首个失败是优惠策略，Agent 还需补支付重试重复扣库存测试。
uv run ai-test-officer demo run --scenario promotion-chain --planner-mode agent-strict --allow-temp-test-code

# 首个失败是退款越权，Agent 还需补 shipped 状态退款测试。
uv run ai-test-officer demo run --scenario refund-guard --planner-mode agent-strict --allow-temp-test-code
```

比赛入口填写的 TAPD/MR 链接均为模拟数据；真实只读接入与安全边界见 [`docs/比赛展示说明.md`](docs/比赛展示说明.md)。

当前比赛入口包含 8 个 TAPD/MR 一一对应的独立 `agent-strict` 脱敏回放。默认复杂案例
`task-45` 支持暂停、1×/2×、重新播放和跳到结论，并展示运行来源、失败驱动补测和运行后
上下文摘要；`task-53` 会展示安全策略真实拒绝远端写请求。

推荐先跑一键彩排脚本：

```bash
scripts/showcase_release_guard.sh
```

脚本会生成报告、导出 FUE 静态包，并运行 `demo doctor` 检查公开包是否脱敏。

最终提交前运行完整比赛门禁。默认会重新执行 8 个 Agent 案例；本地快速复核已保存的
忽略目录回放时，可以显式启用复用模式：

```bash
scripts/competition_check.sh

# 仅用于本地快速复核，不替代最终重新执行
AI_TEST_OFFICER_REUSE_REPLAYS=1 scripts/competition_check.sh
```

门禁包含 Python 测试、前端构建与依赖审计、8 回放契约、公开包脱敏和 Playwright 浏览器 E2E。

也可以手动执行：

```bash
uv run ai-test-officer demo showcase \
  --scenario release-guard \
  --demo-root runs/demos \
  --runs-root runs/showcase \
  --planner-mode agent-strict \
  --run-id release-guard-showcase \
  --export-fue runs/edgeone-site/release-guard-showcase \
  --notify-dry-run
```

检查导出的 FUE public 目录：

```bash
uv run ai-test-officer demo doctor \
  --fue-public runs/edgeone-site/release-guard-showcase/public
```

这条命令会生成报告并导出可部署的静态包。**比赛展示和对外交付默认使用 EdgeOne Makers**：
按 [`docs/部署.md`](docs/部署.md) 完成部署、获取预览链接，再前往[大赛官网](https://portal.learn.woa.com/pages/activityLaodingPage/index.html?scheme_type=aiBlock&from=xx#topics)提交作品；只有官网已上传作品链接才算成功参赛。之后可继续迭代作品，建议尽早提交 Demo 或说明文档，以参与早鸟激励等活动。

拿到 EdgeOne 预览链接后，再用主演示结果和该链接发企微摘要：

公开 `public/` 中只包含可分享的 `index.html`、`report.md`、脱敏 `public-run.json`
和证据文件；完整 `run.json`、日志和本地绝对路径继续只留在 `runs/<run-id>/`。

```bash
uv run ai-test-officer demo showcase \
  --scenario release-guard \
  --demo-root runs/demos \
  --runs-root runs/showcase \
  --planner-mode agent-strict \
  --run-id release-guard-showcase \
  --export-fue runs/edgeone-site/release-guard-showcase \
  --detail-url https://<your-edgeone-preview-url>/ \
  --send
```

企微手机端优先点击 EdgeOne 链接。开发机 `http://<host>:8788` 只用于本地调试，
不建议作为现场或手机端最终链接。

真实 MR 验证使用通用的 `run --mr-url` 或 `batch mr` 入口。真实 URL、diff、日志和报告
只保存在本地忽略目录，不作为仓库内置案例提交。运行过程只在 `runs/` 隔离副本中测试，
不会评论 MR、push、checkout 原始业务仓库或部署环境。

无模型彩排时可以把 `--planner-mode agent-strict` 换成
`--planner-mode deterministic`，用于检查 HTML/FUE/企微格式；正式演示应使用
`agent-strict`，这样报告会展示 Agent 多轮工具调用和关键工具检查。

The synthetic `fullstack` scenario remains available as an additional development
example for code diff analysis, temporary tests, API checks, browser evidence,
and HTML reporting. It is not the primary competition flow.

```bash
uv run ai-test-officer demo create \
  --scenario fullstack \
  --demo-root runs/demos

uv run ai-test-officer demo run \
  --scenario fullstack \
  --demo-root runs/demos \
  --planner-mode agent \
  --allow-temp-test-code
```

The demo intentionally introduces a checkout discount bug in the last commit.
Without Playwright installed, the browser test is skipped with a clear
dependency message while unit/API tests still expose the regression. With
Playwright installed, the browser test saves screenshot evidence under the run
workspace.

本地调试时，也可以把 HTML 发布到开发机静态服务并发企微链接：

```bash
uv run ai-test-officer report serve \
  --root runs/report-site \
  --host 0.0.0.0 \
  --port 8788

uv run ai-test-officer demo run \
  --scenario fullstack \
  --demo-root runs/demos \
  --planner-mode agent \
  --allow-temp-test-code \
  --publish \
  --site-root runs/report-site \
  --report-base-url http://<internal-host>:8788 \
  --send
```

这个方式依赖开发机网络可达性；如果企微手机端打不开，改用 FUE。

### 可选：FUE 静态托管

FUE 静态托管可用于内部分享。它把一次运行的报告 + 实时执行仪表盘回放页
（`public/dashboard/`）打包成静态 Web 应用。完整、带排错步骤的部署说明会随每次导出
自动生成在 `runs/fue-site/<run-id>/FUE_DEPLOY.md`，**部署前请先读它**。下面是与该文档
对齐的精简步骤。

### 前置条件

- Node.js ≥ 18 + npm（用于 FUE CLI）。
- 能访问 FUE 内网并有 FUE 账号；安装并登录 CLI：
  ```bash
  npm i -g @tencent/fue-cli
  fue login
  fue whoami
  ```
- 仪表盘需要前端先构建（否则导出包不含 `public/dashboard/`）：
  ```bash
  cd frontend && npm install && npm run build && cd ..
  ```

### 1) 导出 FUE 包

```bash
uv run ai-test-officer report export-fue \
  --report runs/<run-id>/report.md \
  --output runs/fue-site/<run-id> \
  --project-slug ai-test-officer-report
```

导出后确认 `runs/fue-site/<run-id>/public/dashboard/events.jsonl` 存在且非空。

### 2) 部署（任选其一）

**控制台（UI）**：在 FUE 新建静态 Web 应用，关联 `runs/fue-site/<run-id>/` 目录，
配置按下面填写后部署：

- 工程类型: 静态Web应用
- 框架预设: Other
- 部署方式: 静态托管 (COS + CDN)
- **Static Directory: `public`**
- 访问路径: `/`

**CLI**：

```bash
cd runs/fue-site/<run-id>
fue project create     # 已有项目用 fuse link
fue deploy --cwd . --default
```

### 3) 访问

部署后 FUE 分配 `https://<标识>.fue.woa.com/`：

- 主报告页：`/`
- 实时仪表盘回放页：`/dashboard/?mode=static`（无需后端，读取同目录 `events.jsonl` 还原全过程）

部署成功后把该地址作为 showcase 通知的 `--detail-url`。

For internal FUE sharing, the test environment default `*.fue.woa.com` HTTPS
domain is enough. Competition delivery should use EdgeOne Makers and then be
submitted through the competition website; custom domain, DNS/CNAME, and
certificate work are only needed for a formal business domain.

## 实时执行仪表盘（可视化）

比赛方向要求「用图形化界面或实时展示方式呈现测试过程与结果」。本项目的
`agent-sdk-agent` 在每次运行时把结构化事件追加写入 `runs/<run-id>/events.jsonl`
（阶段进度、工具调用、命令执行、证据、最终结论），并用一个 React 仪表盘实时渲染：

- 阶段进度条（准备→规划→执行→校验→报告）
- 工具调用时间线（实时 spinner / ✓ / ✗，淡入滚动）
- Agent 测试计划执行板（计划项状态、失败驱动补测、命令定位联动）
- 策略形成面板（为什么测这些）
- Agent 运行来源（运行模式、严格工具检查、模型自主工具数和生成测试数）
- 静态回放控制（暂停、倍速、重新播放、跳到结论和事件进度）
- 失败驱动补测与真实安全策略拦截证据
- 运行结束后的结构化上下文摘要与原始隔离证据回读说明
- 执行状态与实时风险/结论
- 失败定位（命令/工具失败时红框高亮 + 自动滚动 + 日志/证据链接）
- 证据网格（截图/日志实时涌入）
- 结束后展示大结论徽章并提供完整报告链接

### 开发机实时直播

```bash
# 推荐：启动任务工作台，在浏览器中选择一一对应的 TAPD/MR、生成计划并点击执行
uv run ai-test-officer dashboard --runs-root runs/live-runs --host 127.0.0.1 --port 8789

# 运行并同时打开实时仪表盘（默认 http://127.0.0.1:8789/?run_id=<id>）
uv run ai-test-officer demo run \
  --scenario fullstack \
  --demo-root runs/demos \
  --planner-mode agent \
  --allow-temp-test-code \
  --visualize

# 或对一个已完成的 run 启动仪表盘用于回放
uv run ai-test-officer report serve --live --run-id <id>
```

### 构建前端（部署 / FUE 前必做）

后端保持标准库（`http.server`），仅前端引入 React/Vite。`ruff` 不覆盖 `frontend/`，
需要先手动构建：

```bash
cd frontend
npm install
npm run build      # 产物输出到 frontend/dist/
npm run typecheck  # 可选：类型检查
```

未构建时，`--visualize` 打开的页面会提示「前端未构建」。

### 可分享回放页（FUE）

`report export-fue` 会把 `frontend/dist` 一并打进 FUE 静态包的
`public/dashboard/`，并附带本次运行的 `events.jsonl`、证据与日志。部署后无需后端
即可按原始事件顺序动态复盘：

```text
https://<your-fue-domain>/dashboard/?mode=static
```

仪表盘在该模式下逐步播放同目录的 `events.jsonl`，完整还原 Agent 测试计划、阶段、工具调用、
策略形成、失败定位与证据网格（详见导出包内的 `FUE_DEPLOY.md`）。线上静态包不持有
模型密钥；真正的一键执行只在上述本地任务工作台中启用。

Run a read-only MR/local range analysis:

```bash
uv run ai-test-officer run \
  --mr-url https://git.woa.com/example/project/-/merge_requests/10 \
  --allow-temp-test-code \
  --task "分析这个 MR 的测试风险并执行本地安全验证"
```

For MR URLs, the runner reads Gongfeng with `GONGFENG_ACCESS_TOKEN`, resolves a
local checkout from `AI_TEST_OFFICER_REPO_ROOTS`, and writes MR metadata plus
per-file diff artifacts under `runs/<run-id>/context/`. Pass
`--repo /path/to/local/checkout` to use an explicit checkout.

```bash
uv run ai-test-officer run \
  --repo /path/to/business-repo \
  --git-range "<base>..<head>" \
  --task "分析这次改动的测试风险并执行本地安全验证"
```

Allow generated temporary test code in the isolated workspace:

```bash
uv run ai-test-officer run \
  --repo /path/to/business-repo \
  --git-range "<base>..<head>" \
  --allow-temp-test-code \
  --task "生成必要的临时测试并验证这次改动"
```

Send a compact WeCom summary after the run:

```bash
uv run ai-test-officer run \
  --repo /path/to/business-repo \
  --git-range "<base>..<head>" \
  --allow-temp-test-code \
  --send \
  --task "生成必要的临时测试并验证这次改动"
```

Render the WeCom payload without sending:

```bash
uv run ai-test-officer run \
  --repo /path/to/business-repo \
  --git-range "<base>..<head>" \
  --notify-dry-run \
  --task "检查通知内容"
```

Outputs are written to:

- `runs/<run-id>/report.md`
- `runs/<run-id>/run.json`
- `runs/<run-id>/report.html`
- `runs/<run-id>/events.jsonl`：运行过程事件流（阶段/工具调用/命令/证据/结论），用于实时仪表盘
- `runs/<run-id>/repo/`
- `runs/<run-id>/context/`
- `runs/<run-id>/logs/`
- `runs/<run-id>/evidence/`

## Local Test Execution

The source repository is never modified. Each run makes an isolated copy in
`runs/<run-id>/repo/`, applies the selected git range there, and only executes
commands from the test whitelist.

The current MVP uses deterministic rules for test selection:

- Go changes run `go test ./<changed-dir> -count=1 -v`.
- Python changes run `python -m unittest discover -s tests -p test_*.py -v`
  when a `tests/` directory exists.
- TypeScript/Jest changes can run package-local `npm --prefix <package> test`.
- Playwright spec/config changes can run package-local e2e scripts discovered
  from the nearest `package.json`.
- Rust changes can run `cargo test --workspace`.
- With `--allow-temp-test-code`, the runner can write temporary test files only
  under allowed test/evidence paths inside the isolated copy.

Those rules are intentionally conservative. They are not committed to the
business repo and can be replaced later by richer Agents SDK tool-calling logic.

## Context And Memory

Do not assume the Agents SDK will always compress oversized input for every
provider. OpenAI Responses API can use truncation or compaction settings, but
the Doubao/Ark path currently uses the OpenAI-compatible Chat Completions mode.
For that path this project keeps its own context layer: large diffs are split
into per-file artifacts under `runs/<run-id>/context/diffs/`, `run.json` stores
only indexes and summaries, and the model receives structured context plus
failure excerpts instead of raw full diffs/logs.

## Tool-Calling Smoke

Verify that the configured model can call local function tools and execute a
synthetic unittest:

```bash
uv run ai-test-officer smoke tools --run-id doubao-tool-smoke
```

The smoke result is written under `runs/<run-id>/tool-smoke.json`.

Verify project MCP config shape:

```bash
uv run ai-test-officer smoke mcp
```

### Internal platform access

Use `mcporter-internal` for internal platforms such as TAPD and iWiki. It uses
the local Taihu login and loads only the requested tool schema, so these
platforms are intentionally not registered as always-on Codex MCP servers.

On a new machine, complete the browser-based authorization once for each
service; this stores the local authorization and does not require a PAT token.

```bash
# One-time local authorization; follow the browser prompt.
mcporter-internal --config config/mcporter.json auth tapd
mcporter-internal --config config/mcporter.json auth iwiki

# Check the configured services.
mcporter-internal --config config/mcporter.json list

# TAPD: find a suitable tool, then execute it.
mcporter-internal --config config/mcporter.json call tapd.lookup_tapd_tool \
  --args '{"task_description":"查询需求详情"}'

# iWiki: call an iWiki tool on demand.
mcporter-internal --config config/mcporter.json call \
  "iwiki.aiSearchDocument(query: '测试方案', limit: 5)"
```

Do not add `TAI_PAT_TOKEN`, TAPD tokens, or iWiki endpoints to `.env` or
`.codex/config.toml` for this workflow.

## Verification

Run the complete competition release gate:

```bash
scripts/competition_check.sh
```

To include the configured model-backed `agent-strict` tool-loop contract:

```bash
AI_TEST_OFFICER_REQUIRE_AGENT=1 scripts/competition_check.sh
```

The gate creates a unique ignored directory under `runs/competition-check/` on
every invocation, so repeated rehearsals never overwrite earlier evidence.

Individual checks remain available:

```bash
uv lock --check
uv run ruff check .
uv run python -m unittest discover -s agents-sdk-agent/tests -p 'test_*.py' -v
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Do not commit `runs/`, `.env`, `.mcp.json`, generated reports, real business
diffs, logs, screenshots, or private tokens.
