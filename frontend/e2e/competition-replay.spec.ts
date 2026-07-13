import { expect, test, type Page } from "@playwright/test";

const tasks = ["42", "43", "45", "46", "47", "48", "53", "55"];

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  if (!process.env.COMPETITION_PACKAGE_DIR) {
    await installSyntheticReplayRoutes(page);
  }
});

test("keeps eight TAPD and MR tasks mapped to their own replay", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".task-card")).toHaveCount(8);
  await expect(page.locator(".task-card", { hasText: "TAPD-114516" })).toContainText("MR !45");

  await page.locator(".task-card", { hasText: "TAPD-114515" }).click();
  await expect(page.locator(".plan-builder")).toContainText("优惠上限调整与契约同步");
  await expect(page.locator("a.replay-button")).toHaveAttribute("href", /replay=task-43/);
});

test("replays pass and blocked decisions with Agent evidence", async ({ page }) => {
  await page.goto("/?mode=static&replay=task-45");
  await expect(page.getByText("建议阻断", { exact: true })).toBeVisible();
  await expect(page.getByText("Agent 工具调用", { exact: false })).toBeVisible();
  await expect(page.getByText("上下文记忆压缩", { exact: true })).toBeVisible();
  await expect(page.getByText("安全隔离边界", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("复盘完成", { exact: true })).toBeVisible();

  await page.goto("/?mode=static&replay=task-43");
  await expect(page.getByText("建议发布", { exact: true })).toBeVisible();
  await expect(page.getByText("风险等级：low", { exact: true })).toBeVisible();
});

test("fits the competition workbench on a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "TAPD × 工蜂 MR" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("controls static replay speed, pause, skip, and restart", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/?mode=static&replay=task-45");
  const controls = page.getByLabel("回放控制");
  await expect(controls).toBeVisible();
  await controls.getByRole("button", { name: "暂停" }).click();
  const progress = controls.locator(".replay-progress");
  const pausedAt = await progress.textContent();
  await page.waitForTimeout(700);
  await expect(progress).toHaveText(pausedAt ?? "");
  await controls.getByRole("button", { name: "2×" }).click();
  await controls.getByRole("button", { name: "继续" }).click();
  await controls.getByRole("button", { name: "跳到结论" }).click();
  await expect(page.getByText("建议阻断", { exact: true })).toBeVisible();
  await controls.getByRole("button", { name: "重新播放" }).click();
  await expect(controls.getByRole("button", { name: "暂停" })).toBeEnabled();
});

async function installSyntheticReplayRoutes(page: Page): Promise<void> {
  const items = tasks.map((id) => ({
    task_id: `task-${id}`,
    run_id: `task-${id}`,
    scenario: id === "43" ? "promotion-chain-pass" : "release-guard",
    verdict: id === "43" || id === "46" || id === "48" ? "pass" : "fail",
    risk: id === "43" || id === "46" || id === "48" ? "low" : "high",
    tool_calls: 4,
    planner_steps: 3,
    compression_ratio: 0.42,
  }));
  await page.route("**/api/capabilities", (route) => route.fulfill({ status: 404, body: "not found" }));
  await page.route("**/api/replays", (route) => route.fulfill({ status: 404, body: "not found" }));
  await page.route("**/replays/manifest.json", (route) =>
    route.fulfill({ json: { default_task_id: "task-45", items } })
  );
  await page.route("**/replays/*/events.jsonl", (route) => {
    const taskId = new URL(route.request().url()).pathname.split("/").at(-2) ?? "task-45";
    route.fulfill({ contentType: "application/x-ndjson", body: replayEvents(taskId) });
  });
  await page.route("**/replays/*/report.html", (route) =>
    route.fulfill({ contentType: "text/html", body: "<h1>脱敏测试报告</h1>" })
  );
}

function replayEvents(taskId: string): string {
  const passes = ["task-43", "task-46", "task-48"].includes(taskId);
  const eventData: Array<[string, Record<string, unknown>]> = [
    ["context", { task: `${taskId} 合成测试`, changed_files: [{ status: "M", path: "orders.py" }] }],
    ["isolation", { workspace: "isolated-copy" }],
    ["phase", { phase: "planning", status: "start" }],
    ["planner", { step: "读取需求与 diff，选择风险验证" }],
    ["tool_call", { id: "tool-1", tool: "read_file_diff", status: "ok", output: "diff reviewed" }],
    ["command", { id: "command-1", command: "python -m unittest", status: passes ? "ok" : "fail", returncode: passes ? 0 : 1 }],
    ["evidence", { path: "evidence/result.txt", kind: "log", caption: "脱敏证据" }],
    ["memory", { mode: "structured", source_chars: 1000, summary_chars: 420, compression_ratio: 0.42, artifact_count: 2 }],
    ["verdict", { verdict: passes ? "pass" : "fail", risk: passes ? "low" : "high", summary: passes ? "修复验证通过" : "发现发布阻断风险" }],
    ["done", {}],
  ];
  return eventData
    .map(([type, data], index) => JSON.stringify({ seq: index + 1, ts: index + 1, type, data }))
    .join("\n");
}
