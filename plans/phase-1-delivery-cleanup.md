# 阶段一细化：代码与 Git 交付收口

## 1. 阶段目标

把当前 Agents SDK 迁移工作整理成一个可审查、可从干净 checkout 复现的 Git 版本。在完成分类和验证前，不删除、不移动、不提交归属不明确的文件。

## 2. 当前盘点

### 已确认的活动实现

- `agents-sdk-agent/`：当前 Python 后端、CLI 和测试，必须保留并纳入版本管理。
- `frontend/`：React/Vite 实时仪表盘，源码和 lockfile 应纳入版本管理；`node_modules/`、`dist/` 不提交。
- `pyproject.toml`：当前包发现路径已经指向 `agents-sdk-agent/src`。
- `.github/workflows/ci.yml`：当前测试目录已经指向 `agents-sdk-agent/tests`。
- `scripts/showcase_release_guard.sh`：比赛主演示脚本，保留。
- `scripts/showcase_agent_loop.sh`：快速兜底脚本，保留。
- `plans/`：比赛优化与执行记录，保留。

### 已确认的归档实现

- `codex-agent/`：旧 Codex SDK 实现，仅作为参考归档。
- 归档目录不得参与 setuptools 包发现、默认测试、CI 或比赛主演示。
- 需要确认其中是否包含重复、过期、敏感或不适合公开提交的历史材料。

### 已确认的旧路径删除

当前根目录下旧实现已删除，迁移方向与 `pyproject.toml`、CI 一致：

- `src/ai_test_officer/`
- `tests/`
- `scripts/create_scenario_a_demo.py`
- `scripts/create_scenario_demos.py`
- `examples/sample_pr_diff.txt`

提交前需要建立旧路径到新路径的迁移映射，避免误删仍未迁移的能力。

### 已确认的生成或本地产物

- `runs/`：约 2.7 GB，本地运行工作区和报告，不提交内容。
- `frontend/node_modules/`：前端依赖，不提交。
- `frontend/dist/`：前端构建结果，不提交。
- `core.1694096`：core dump，不提交。
- `.fue/*.log`：本地 FUE 日志，不提交。
- `.playwright-mcp/*.log`：本地 Playwright 日志，不提交。

### 待确认是否纳入仓库

- `.agents/skills/edgeone-makers-*`
- `.agents/skills/makers-*`
- `skills-lock.json`
- `.codebuddy/`
- `config/mcporter.json`
- `docs/image.png`
- `fue-docs-overview.md`
- `docs/demo-cases/`
- `docs/dev-issues/`
- `docs/fue-report-hosting.md`
- `docs/复现说明.md`
- `docs/比赛展示说明.md`
- `docs/部署.md`

判断原则：比赛运行、干净 checkout、EdgeOne 部署或必要说明直接依赖的内容才纳入；纯本机工具缓存、重复资料或内部敏感内容不纳入。

## 3. `.gitignore` 目标规则

必须覆盖：

```gitignore
.venv/
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/

.env
.env.*
!.env.example
.mcp.json
.mcp.local.json

frontend/node_modules/
frontend/dist/
dist/
build/

runs/*
!runs/.gitkeep
reports/*
!reports/.gitkeep

.playwright-mcp/
.fue/
.edgeone/
.tef_dist/
core
core.*
```

需要决定是否恢复 `runs/.gitkeep` 和 `reports/.gitkeep`。按照仓库 `AGENTS.md`，`reports/.gitkeep` 应默认保留；`runs/.gitkeep` 可保留以表达目录用途。

## 4. 旧实现迁移核对

逐项核对以下能力是否已在 Agents SDK 实现中覆盖：

| 旧能力 | 新位置 | 状态 |
| --- | --- | --- |
| CLI | `agents-sdk-agent/src/ai_test_officer/cli.py` | 待核对参数覆盖 |
| Codex/Agent 执行 | `agent/`、`execution/` | 待核对 |
| Demo scenarios | `demo/` | 待核对 A/B/C 迁移关系 |
| doctor | `showcase_doctor.py`、`mcp/smoke.py` | 待核对 |
| git diff | `tools/git.py`、`git_tools.py` | 待核对重复模块 |
| models | `models.py` | 待核对 |
| prompts | `prompts/` | 待核对 |
| report | `report.py`、`report_site.py` | 待核对 |
| visualization | `events.py`、`live_server.py`、`frontend/` | 待核对 |
| WeCom | `integrations/wecom.py`、`notify.py` | 待核对重复职责 |

只有核对完成后，才能确认旧根目录删除是完整迁移而非功能丢失。

## 5. 执行步骤

### 1A：安全与忽略规则

- [x] 修复 `.gitignore` 尾随空格和重复 `.env`。
- [x] 增加 `frontend/node_modules/`、`frontend/dist/` 和 `core.*`。
- [x] 确认 `.fue/`、`.playwright-mcp/`、`.edgeone/` 和 `.tef_dist/` 完整忽略。
- [x] 恢复或创建 `runs/.gitkeep`、`reports/.gitkeep`。
- [x] 使用 `git check-ignore -v` 验证规则。
- [x] 扫描本批次待提交文件中的密钥与 Webhook 模式。

### 1B：迁移完整性

- [x] 生成旧根实现与 Agents SDK 实现的模块映射。
- [x] 核对所有旧 CLI 能力的去留。
- [x] 查找新实现中的重复模块和兼容转发模块。
- [x] 确认 `codex-agent/` 只保留 Git 历史指针，不被包发现、CI 或默认命令加载。
- [x] 确认活动文档使用 Agents SDK 新入口；真实 MR 改用通用只读入口。

### 1C：依赖与干净环境

- [x] 检查 `pyproject.toml` 与 `uv.lock` 一致。
- [x] 检查前端 `package.json` 与 `package-lock.json` 一致。
- [x] 从独立索引快照执行干净安装。
- [x] 执行 Python、前端和 CLI smoke 验证。
- [x] 检查验证过程没有修改源工作区。

### 1D：提交边界

- [x] 审查最终 `git diff --stat`。
- [x] 审查最终 `git diff --check`。
- [x] 审查所有新增大文件。
- [x] 确认不存在生成报告、截图、日志和真实 diff。
- [x] 相关测试全部通过后提交。
- [ ] 按仓库要求推送 `origin/main`。

## 6. 阶段完成定义

满足以下条件才可勾选主计划中的“阶段一完成”：

1. 当前活动实现全部受 Git 管理。
2. 本地产物和敏感文件全部被忽略。
3. 旧实现删除已完成能力映射核对。
4. 干净 checkout 可以安装、测试、构建和运行 CLI。
5. 后端、前端、lock 和格式检查全部通过。
6. 迁移提交已经推送到 `origin/main`。

## 7. 下一步

执行 1B“迁移完整性”：生成旧实现到 Agents SDK 实现的模块和 CLI 能力映射，确认归档边界及新实现中的重复职责。

## 8. 执行记录

### 2026-07-13：1A 安全基线

- `.gitignore` 已覆盖本地环境、模型/MCP 配置、前端依赖与构建、运行报告、工具日志、EdgeOne 产物和 core dump。
- `reports/.gitkeep` 已恢复，`runs/.gitkeep` 已创建。
- `git diff --check` 通过。
- `git check-ignore -v` 已确认 core dump、`frontend/node_modules`、`frontend/dist`、`.fue`、`.playwright-mcp`、`runs/*` 和 `reports/*` 命中预期规则。
- 本批次秘密模式扫描无命中。
- `uv lock --check` 和 `uv run ruff check .` 通过。

### 2026-07-13：1B/1C Agents SDK 迁移收口

- 活动实现已统一到 `agents-sdk-agent/`；旧 Codex SDK 完整实现保留在 Git 历史 `802cac9`，当前树只保留归档指针。
- 移除仓库内置真实 MR 案例、真实服务名、个人 workspace 默认路径和个人环境标识；通用 `run --mr-url`、`batch mr` 能力保留。
- JavaScript 测试规划改为从最近的 `package.json` 通用发现测试脚本。
- 修复公开导出对预先存在 `frontend/dist` 的隐式依赖；未构建前端时生成最小安全回放页。
- Vite 升级到 `8.1.4`，`@vitejs/plugin-react` 升级到 `6.0.3`，`npm audit` 为 0。
- 主工作区和独立索引快照均通过 83 个后端测试、Ruff、lock 检查、CLI smoke、前端 typecheck/build 和依赖审计。
- 批次零本地提交为 `e64485d`；GitHub HTTPS 凭据缺失，推送待统一重试。
