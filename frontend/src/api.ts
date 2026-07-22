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

export interface PlaybackState {
  current: number;
  total: number;
  paused: boolean;
  speed: number;
  finished: boolean;
}

export interface StreamHandle {
  close: () => void;
  pause?: () => void;
  resume?: () => void;
  restart?: () => void;
  setSpeed?: (speed: number) => void;
  skipToEnd?: () => void;
}

export async function getReplayCatalog(): Promise<ReplayCatalog | null> {
  const paths = isStaticPackage()
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
  if (isStaticPackage()) return null;
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
export function isStaticPackage(): boolean {
  return document
    .querySelector('meta[name="ai-test-officer-runtime"]')
    ?.getAttribute("content") === "static";
}

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
  onClose: () => void,
  onReset?: () => void,
  onPlaybackState?: (state: PlaybackState) => void
): StreamHandle {
  if (isStaticReplay()) {
    const controller = new StaticReplayController(onEvent, onClose, onReset, onPlaybackState);
    controller.start();
    return controller;
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

  return { close: () => source.close() };
}

class StaticReplayController implements StreamHandle {
  private events: AppEvent[] = [];
  private index = 0;
  private paused = false;
  private speed = new URLSearchParams(window.location.search).get("judge") === "1" ? 2 : 1;
  private closed = false;
  private finished = false;
  private generation = 0;
  private wake: (() => void) | null = null;

  constructor(
    private readonly onEvent: (event: AppEvent) => void,
    private readonly onClose: () => void,
    private readonly onReset?: () => void,
    private readonly onPlaybackState?: (state: PlaybackState) => void
  ) {}

  start(): void {
    void this.loadAndPlay();
  }

  close(): void {
    this.closed = true;
    this.generation += 1;
    this.signal();
  }

  pause(): void {
    if (this.finished) return;
    this.paused = true;
    this.publish();
  }

  resume(): void {
    if (this.finished) return;
    this.paused = false;
    this.signal();
    this.publish();
  }

  restart(): void {
    if (this.closed || this.events.length === 0) return;
    this.generation += 1;
    this.signal();
    this.index = 0;
    this.paused = false;
    this.finished = false;
    this.onReset?.();
    this.publish();
    void this.play(this.generation);
  }

  setSpeed(speed: number): void {
    if (![0.5, 1, 2].includes(speed)) return;
    this.speed = speed;
    this.signal();
    this.publish();
  }

  skipToEnd(): void {
    if (this.finished) return;
    this.paused = false;
    this.speed = 2;
    this.signal();
    while (this.index < this.events.length) {
      this.onEvent(this.events[this.index]);
      this.index += 1;
    }
    this.finish();
  }

  private async loadAndPlay(): Promise<void> {
    try {
      const taskId = replayTaskId();
      const path = taskId ? `replays/${encodeURIComponent(taskId)}/events.jsonl` : "events.jsonl";
      const response = await fetch(path, { cache: "no-store" });
      if (!response.ok) {
        this.finish();
        return;
      }
      const text = await response.text();
      this.events = text
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .flatMap((line) => {
          try {
            return [JSON.parse(line) as AppEvent];
          } catch {
            return [];
          }
        });
      this.publish();
      await this.play(this.generation);
    } catch {
      this.finish();
    }
  }

  private async play(generation: number): Promise<void> {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    while (!this.closed && generation === this.generation && this.index < this.events.length) {
      while (this.paused && !this.closed && generation === this.generation) {
        await this.waitForSignal();
      }
      if (this.closed || generation !== this.generation) return;
      const event = this.events[this.index];
      this.onEvent(event);
      this.index += 1;
      this.publish();
      if (!reduceMotion && event.type !== "done" && this.index < this.events.length) {
        await this.delay(replayDelay(event) / this.speed);
      }
    }
    if (!this.closed && generation === this.generation) this.finish();
  }

  private finish(): void {
    if (this.finished) return;
    this.finished = true;
    this.paused = false;
    this.publish();
    this.onClose();
  }

  private publish(): void {
    this.onPlaybackState?.({
      current: this.index,
      total: this.events.length,
      paused: this.paused,
      speed: this.speed,
      finished: this.finished,
    });
  }

  private waitForSignal(): Promise<void> {
    return new Promise((resolve) => {
      this.wake = resolve;
    });
  }

  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => {
      const timer = window.setTimeout(() => {
        this.wake = null;
        resolve();
      }, ms);
      this.wake = () => {
        window.clearTimeout(timer);
        this.wake = null;
        resolve();
      };
    });
  }

  private signal(): void {
    this.wake?.();
  }
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
