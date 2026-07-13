import type { AppEvent } from "./types";

export interface ExecutionCapability {
  can_execute: boolean;
  mode: string;
  scenarios: string[];
  busy: boolean;
}

export interface ReplayItem {
  task_id: string;
  run_id: string;
  scenario: string;
  verdict: string;
  risk: string;
  tool_calls: number;
  planner_steps: number;
  compression_ratio: number;
}

export interface ReplayCatalog {
  default_task_id: string;
  items: ReplayItem[];
}

export async function getReplayCatalog(): Promise<ReplayCatalog | null> {
  const paths = isStaticReplay()
    ? ["replays/manifest.json"]
    : ["/api/replays", "replays/manifest.json"];
  for (const path of paths) {
    try {
      const response = await fetch(path, { cache: "no-store" });
      if (!response.ok || !response.headers.get("content-type")?.includes("application/json")) continue;
      return (await response.json()) as ReplayCatalog;
    } catch {
      // Try the static catalog fallback.
    }
  }
  return null;
}

export async function getExecutionCapability(): Promise<ExecutionCapability | null> {
  try {
    const response = await fetch("/api/capabilities", { cache: "no-store" });
    if (!response.ok || !response.headers.get("content-type")?.includes("application/json")) return null;
    return (await response.json()) as ExecutionCapability;
  } catch {
    return null;
  }
}

export async function startDemoExecution(scenario: string): Promise<string> {
  const response = await fetch("/api/demo/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario }),
  });
  const payload = (await response.json()) as { run_id?: string; error?: string };
  if (!response.ok || !payload.run_id) {
    throw new Error(payload.error || "无法启动本地合成测试");
  }
  return payload.run_id;
}

/**
 * Detect the "static replay" mode used by the FUE export. In this mode the
 * dashboard is served as a plain static site with no backend, so it must read
 * `events.jsonl` (and evidence/report files) as sibling static assets instead
 * of talking to the live SSE server.
 */
export function isStaticReplay(): boolean {
  return new URLSearchParams(window.location.search).get("mode") === "static";
}

export function replayTaskId(): string {
  return new URLSearchParams(window.location.search).get("replay") ?? "";
}

export function replayUrl(taskId: string): string {
  const params = new URLSearchParams({ mode: "static", replay: taskId });
  return `?${params.toString()}`;
}

/**
 * Open the run's event stream. For a live server this is SSE; for a static
 * FUE export it replays `events.jsonl` from the same directory. Returns the
 * `EventSource` (or `null` when there is nothing to close in static mode).
 */
export function openStream(
  runId: string,
  onEvent: (event: AppEvent) => void,
  onClose: () => void
): EventSource | null {
  if (isStaticReplay()) {
    void replayStatic(onEvent, onClose);
    return null;
  }

  const url = `/api/events?run_id=${encodeURIComponent(runId)}`;
  const source = new EventSource(url);

  source.onmessage = (ev) => {
    try {
      const parsed = JSON.parse(ev.data) as AppEvent;
      onEvent(parsed);
      if (parsed.type === "done") {
        source.close();
        onClose();
      }
    } catch {
      // Ignore malformed frames.
    }
  };

  source.onerror = () => {
    // EventSource reconnects automatically while the run is live. If the server
    // closed the stream (run finished), we stop here.
    source.close();
    onClose();
  };

  return source;
}

async function replayStatic(
  onEvent: (event: AppEvent) => void,
  onClose: () => void
): Promise<void> {
  try {
    const taskId = replayTaskId();
    const path = taskId ? `replays/${encodeURIComponent(taskId)}/events.jsonl` : "events.jsonl";
    const res = await fetch(path, { cache: "no-store" });
    if (!res.ok) {
      onClose();
      return;
    }
    const text = await res.text();
    const events: AppEvent[] = [];
    for (const line of text.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        events.push(JSON.parse(trimmed) as AppEvent);
      } catch {
        // Ignore malformed frames.
      }
    }
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    for (const event of events) {
      onEvent(event);
      if (!reduceMotion && event.type !== "done") {
        await new Promise((resolve) => window.setTimeout(resolve, replayDelay(event)));
      }
    }
  } catch {
    // Network/file errors: nothing to replay.
  }
  onClose();
}

function replayDelay(event: AppEvent): number {
  if (event.type === "phase") return 260;
  if (event.type === "tool_call" || event.type === "command") return 420;
  if (event.type === "evidence" || event.type === "verdict") return 520;
  return 180;
}

/**
 * Build a URL for an evidence file. In live mode this routes through the
 * backend's `/files/` endpoint (scoped by run_id); in static replay mode the
 * file is a sibling static asset referenced by its run-relative path.
 */
export function fileUrl(runId: string, relPath: string): string {
  const safePath = safeRelativePath(relPath);
  if (!safePath) return "#";
  if (isStaticReplay()) {
    const taskId = replayTaskId();
    return taskId ? `replays/${encodeURIComponent(taskId)}/${safePath}` : safePath;
  }
  return `/files/${safePath}?run_id=${encodeURIComponent(runId)}`;
}

function safeRelativePath(value: string): string | null {
  const normalized = value.replace(/\\/g, "/").replace(/^\/+/, "");
  if (!normalized || normalized.includes("..") || /^[a-z][a-z0-9+.-]*:/i.test(normalized)) {
    return null;
  }
  return normalized;
}

/**
 * Build a URL for the full HTML report. Live mode proxies through the backend;
 * static replay resolves to the sibling `report.html` in the same directory.
 */
export function reportUrl(runId: string): string {
  if (isStaticReplay()) {
    const taskId = replayTaskId();
    return taskId ? `replays/${encodeURIComponent(taskId)}/report.html` : "report.html";
  }
  return `/api/report.html?run_id=${encodeURIComponent(runId)}`;
}
