import type { AppEvent } from "./types";

/**
 * Detect the "static replay" mode used by the FUE export. In this mode the
 * dashboard is served as a plain static site with no backend, so it must read
 * `events.jsonl` (and evidence/report files) as sibling static assets instead
 * of talking to the live SSE server.
 */
export function isStaticReplay(): boolean {
  return new URLSearchParams(window.location.search).get("mode") === "static";
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
    const res = await fetch("events.jsonl", { cache: "no-store" });
    if (!res.ok) {
      onClose();
      return;
    }
    const text = await res.text();
    for (const line of text.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        onEvent(JSON.parse(trimmed) as AppEvent);
      } catch {
        // Ignore malformed frames.
      }
    }
  } catch {
    // Network/file errors: nothing to replay.
  }
  onClose();
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
    return safePath;
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
    return "report.html";
  }
  return `/api/report.html?run_id=${encodeURIComponent(runId)}`;
}
