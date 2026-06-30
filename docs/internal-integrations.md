# Internal Integration Setup

This repository is public-facing demo code. Do not commit real company code,
private diffs, TAPD content, logs, screenshots, or tokens.

## Current State

The current MVP accepts local files through `--diff` and `--requirement`, builds
a Test Officer prompt, runs Codex, and writes a Markdown report. It now includes
a `doctor` command for integration smoke checks and repo-scoped Codex MCP/Skill
configuration for development.

The first internal milestone should be an input adapter layer:

1. Fetch TGit MR metadata and diff.
2. Fetch TAPD story, task, or bug context.
3. Save fetched context to local generated files.
4. Reuse the existing `--diff` and `--requirement` prompt path.

This keeps the core testing workflow runnable while the company integrations are
still changing.

## Local Secrets

Put real values in local `.env`, not in git:

```bash
cp .env.example .env
```

Required for the first internal demo:

| Variable | Use |
| --- | --- |
| `TAPD_ACCESS_TOKEN` | TAPD HTTP MCP authentication. |
| `GONGFENG_ACCESS_TOKEN` | Gongfeng/TGit MR metadata and diff access. |

Optional for later demo polish:

| Variable | Use |
| --- | --- |
| `TAI_PAT_TOKEN` or `IWIKI_MCP_TOKEN` | iWiki context lookup. |
| `WECOM_WEBHOOK_URL` or `WECOM_WEBHOOK_KEY` | WeCom bot report delivery. |

## Codex MCP Configuration

Codex uses `.codex/config.toml` for project-level MCP configuration in trusted
projects. This repository commits only environment-variable references:

- `tapd_mcp_http`: TAPD streamable HTTP MCP using `TAPD_ACCESS_TOKEN`.
- `iWiki`: iWiki streamable HTTP MCP using `TAI_PAT_TOKEN`.
- `gongfeng`: Gongfeng/TGit stdio MCP using `GONGFENG_ACCESS_TOKEN`.
- `playwright`: Playwright stdio MCP for browser evidence capture.

Restart Codex or open a new thread after changing project MCP or repo skills so
the runtime reloads them.

## iWiki Smoke Check

The current iWiki MCP endpoint is already wired in `.codex/config.toml` as
`mcp_servers.iWiki` and uses `TAI_PAT_TOKEN`. The local `.mcp.json` can also
carry the same endpoint for clients that read Claude-style MCP JSON.

Validate through the CLI:

```bash
uv run ai-test-officer doctor
```

A healthy iWiki result is:

```text
[PASS] iWiki MCP: initialize returned serverInfo
```

In this repository the direct MCP smoke also confirmed `initialize`, `tools/list`,
and `aiSearchDocument` for WeCom bot setup docs. If Codex does not show iWiki MCP
tools in the current thread, restart Codex or open a new thread so the project
MCP config is reloaded.

## WeCom Bot Notification

iWiki search found three useful implementation options:

- Direct group bot webhook: create or find the group robot/message push entry,
  copy the webhook address, and send `msgtype=text` or `msgtype=markdown`.
  Relevant docs: [使用群机器人通知](https://iwiki.woa.com/p/79242724) and
  [企业微信消息推送使用说明](https://iwiki.woa.com/p/486273093).
- TOF message service wrapper for WeCom robot messages:
  `POST /ebus/tof4_msg/api/v1/Message/SendWeComRobotInfo`.
  Relevant doc: [TOF FAQ](https://iwiki.woa.com/p/4007825539).
- Cloud function wrapper that accepts `webhookUrl`, `msgType`, `text`, and
  optional card fields. Relevant doc:
  [云函数-WeCom 机器人消息发送接口文档](https://iwiki.woa.com/p/4013901366).

For the MVP, use the direct group bot path because it matches the existing
`camp_workspace` hooks and has no extra service dependency. Prefer storing the
full webhook URL locally:

```bash
WECOM_WEBHOOK_URL=<full webhook URL>
```

The CLI also supports the key-only form:

```bash
WECOM_WEBHOOK_KEY=<key from the webhook URL>
```

Simulate without sending:

```bash
uv run ai-test-officer notify \
  --message "AI Test Officer notify smoke" \
  --dry-run
```

Send a report after setting `WECOM_WEBHOOK_URL` or `WECOM_WEBHOOK_KEY`:

```bash
uv run ai-test-officer notify \
  --report reports/latest-report.md \
  --message "场景A测试报告"
```

## Scenario Demo Commands

Current MVP does not enable WeCom inbound questions or callback receiving. Run
the competition demos directly from the CLI, then optionally send the generated
report summary through the outbound webhook.

Create the synthetic demo repositories:

```bash
uv run ai-test-officer scenario create \
  --scenario all \
  --demo-root /tmp/ai-test-officer-scenarios
```

Dry-run each scenario without calling Codex SDK:

```bash
uv run ai-test-officer scenario run --scenario A --demo-root /tmp/ai-test-officer-scenarios --dry-run
uv run ai-test-officer scenario run --scenario B --demo-root /tmp/ai-test-officer-scenarios --dry-run
uv run ai-test-officer scenario run --scenario C --demo-root /tmp/ai-test-officer-scenarios --dry-run
```

Run one scenario through Codex SDK and push a summary to WeCom:

```bash
uv run ai-test-officer scenario run \
  --scenario A \
  --demo-root /tmp/ai-test-officer-scenarios \
  --send
```

Do not commit or paste the webhook URL/key into GitHub, public docs, reports, or
logs. iWiki notes that code containing a WeCom webhook is a real secret leak, not
a false positive: [代码包含微信webhook是否误报](https://iwiki.woa.com/p/4007134812).

Inbound WeCom group Q&A is intentionally deferred. If it is needed later, design
it as a separate receiving service and keep any receiving secrets local only.

## Local MCP Compatibility Example

If running the workflow through an MCP-capable IDE or CLI, use a local
`.mcp.json` with placeholders replaced on your machine only:

```json
{
  "mcpServers": {
    "tapd_mcp_http": {
      "type": "http",
      "url": "https://mcpgw.knot.woa.com/tapd/",
      "timeout": 20000,
      "transportType": "streamable-http",
      "headers": {
        "X-Tapd-Access-Token": "<TAPD_ACCESS_TOKEN>"
      }
    },
    "gongfeng": {
      "command": "npx",
      "args": ["-y", "@tencent/tgit-mcp-server@latest"],
      "env": {
        "GONGFENG_ACCESS_TOKEN": "<GONGFENG_ACCESS_TOKEN>"
      }
    },
    "iWiki": {
      "type": "http",
      "url": "https://prod.mcp.it.woa.com/app_iwiki_mcp/mcp3",
      "timeout": 20000,
      "transportType": "streamable-http",
      "headers": {
        "Authorization": "Bearer <TAI_PAT_TOKEN>"
      }
    }
  }
}
```

Keep `.mcp.json` local and ignored. It is useful for clients that understand the
Claude-style JSON format, while Codex uses `.codex/config.toml`.

## Skill Workflow

The repo skill lives at `.agents/skills/ai-test-officer/SKILL.md`.

Use the skill for PR/MR testing reports, TAPD bug/story analysis, competition
demo preparation, and the first closed-loop workflow:

```bash
uv run ai-test-officer doctor
uv run ai-test-officer run \
  --repo /path/to/local/repo \
  --last-commit \
  --task "场景A：分析刚提交的改动并跑针对性测试"
```

MCP is the external tool layer. The skill is the reusable testing workflow.

## TAPD Smoke Check

Validate the TAPD MCP endpoint without exposing the token:

```bash
curl -s --max-time 10 -X POST "${TAPD_MCP_URL:-https://mcpgw.knot.woa.com/tapd/}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Tapd-Access-Token: ${TAPD_ACCESS_TOKEN}" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"ai-test-officer","version":"0.1.0"}}}'
```

A healthy response contains `serverInfo`. If it does not, check token validity
and company network access before changing the application code.

## TGit Diff Path

Gongfeng and TGit are treated as one Git/MR platform capability. For the first
implementation, REST is simpler and easier to test than MCP:

1. Use the MR URL to derive `<project>` and `<iid>`.
2. Query MR metadata:

   ```bash
   curl -s -H "PRIVATE-TOKEN: ${GONGFENG_ACCESS_TOKEN}" \
     "https://git.woa.com/api/v3/projects/<url-encoded-project>/merge_request/iid/<iid>"
   ```

3. Read the returned global `id`.
4. Query changes:

   ```bash
   curl -s -H "PRIVATE-TOKEN: ${GONGFENG_ACCESS_TOKEN}" \
     "https://git.woa.com/api/v3/projects/<url-encoded-project>/merge_request/<id>/changes"
   ```

5. Convert `files[].diff` into a local unified diff file and pass it to:

   ```bash
   uv run ai-test-officer run \
     --task "Analyze this MR and produce a targeted test report." \
     --repo /path/to/local/repo \
     --diff /path/to/generated-pr.diff \
     --dry-run
   ```

## Recommended Competition Order

1. Internal config and smoke checks: `uv run ai-test-officer doctor`.
2. Reproducible full-chain demo:

   ```bash
   uv sync --extra codex --extra e2e --group dev
   uv run python -m playwright install chromium
   uv run ai-test-officer scenario create --scenario A-fullstack --demo-root /tmp/ai-test-officer-scenarios
   uv run ai-test-officer scenario run --scenario A-fullstack --demo-root /tmp/ai-test-officer-scenarios --visualize
   ```

3. Optional WeCom push: rerun the scenario with `--send` after `WECOM_WEBHOOK_URL`
   or `WECOM_WEBHOOK_KEY` is configured.
4. CLI adapters: add `--mr-url`, `--tapd-id`, and generated context files.
5. Real internal run: point the same report pipeline at an authorized local
   repository, keeping generated evidence and reports out of GitHub.

The key demo story is: given a PR and optional TAPD bug, the agent understands
intent, chooses tests, runs checks, and writes a decision-ready report.
