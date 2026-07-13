# FUE Report Hosting（内部分享与备用）

AI Test Officer 的报告可以导出为 FUE 静态 Web 应用，避免企微手机端访问开发机 IP/端口失败。
比赛正式提交默认使用 EdgeOne Makers；本文只描述内部分享和备用托管路径。

## 结论

- 内部 demo 用 FUE 测试环境默认 `*.fue.woa.com` HTTPS 域名即可。
- 不需要先申请自有域名、CNAME 或 HTTPS 证书。
- 需要有 FUE 登录态，以及一个可部署的 FUE 项目/团队权限。
- 只有要绑定正式业务域名时，才需要业务侧准备 DNS/CNAME 和证书。

## 生成静态包

备用演示推荐使用快速 `agent-loop` 脚本生成报告、导出 FUE 包并做脱敏检查：

```bash
scripts/showcase_agent_loop.sh
```

也可以手动用 showcase 生成报告并导出 FUE 包：

```bash
uv run ai-test-officer demo showcase \
  --scenario agent-loop \
  --demo-root runs/demos \
  --runs-root runs/showcase \
  --planner-mode agent-strict \
  --run-id agent-loop-showcase \
  --export-fue runs/fue-site/agent-loop-showcase \
  --notify-dry-run
```

也可以对已有报告单独导出：

```bash
uv run ai-test-officer report export-fue \
  --report runs/<run-id>/report.md \
  --output runs/fue-site/<run-id> \
  --project-slug ai-test-officer-report
```

生成目录结构：

```text
runs/fue-site/<run-id>/
  fue.json
  package.json
  FUE_DEPLOY.md
  public/
    index.html
    report.md
    public-run.json
    repo/reports/evidence/*.png
```

`public-run.json` 是脱敏后的公开记录，只保留结论、工具轨迹、命令退出码、短摘要和相对证据路径；完整 `run.json` 继续只保存在本机 `runs/<run-id>/`。

部署前建议检查一次：

```bash
uv run ai-test-officer demo doctor \
  --fue-public runs/fue-site/agent-loop-showcase/public
```

如果要检查已经拿到的 FUE 链接是否会用于企微发送：

```bash
uv run ai-test-officer demo doctor \
  --fue-public runs/fue-site/agent-loop-showcase/public \
  --detail-url https://<your-fue-domain>/index.html \
  --require-detail-url
```

## FUE 配置

控制台创建项目时选择：

- 工程类型：静态Web应用
- 框架预设：Other
- 部署方式：静态托管（COS + CDN）
- Static Directory：`public`
- 访问路径：`/`

CLI 首次使用：

```bash
npm i -g @tencent/fue-cli --registry=https://mirrors.tencent.com/npm/
fue login
fue project create
fue deploy --cwd runs/fue-site/<run-id> --default
```

如果项目已创建：

```bash
fue link
fue deploy --cwd runs/fue-site/<run-id> --default
```

部署成功后，用 FUE 返回的 HTTPS 链接发企微摘要：

```bash
uv run ai-test-officer demo showcase \
  --scenario agent-loop \
  --demo-root runs/demos \
  --runs-root runs/showcase \
  --planner-mode agent-strict \
  --run-id agent-loop-showcase \
  --export-fue runs/fue-site/agent-loop-showcase \
  --detail-url https://<your-fue-domain>/index.html \
  --send
```

企微消息只包含场景、结论、风险、核心结果和完整报告链接，不发送本地绝对路径、prompt、diff 或 token。

## 当前本机状态

- Node.js 版本满足 FUE CLI 要求。
- `@tencent/fue-cli` 可从内部 npm 拉取。
- 本机尚未有 FUE 登录态，`fue status --ni` 会触发设备授权登录。

下一步需要人工完成 FUE 登录和项目创建/关联。部署成功后，把 FUE 返回的默认域名作为后续企微通知链接。

开发机 `http://<host>:8788` 静态服务只建议用于本地调试。手机端、评审现场和群内分享优先使用 FUE 链接。
