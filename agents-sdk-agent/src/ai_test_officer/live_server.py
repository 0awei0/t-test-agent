"""Lightweight live dashboard server (stdlib only).

Serves the built React dashboard and streams a run's ``events.jsonl`` to browsers
over Server-Sent Events. The same endpoint also supports replaying a finished
run: if ``events.jsonl`` already ends with a ``done`` event, the server streams
the full history and then closes.
"""

from __future__ import annotations

import json
import mimetypes
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

# Poll interval for tailing the events file and the idle timeout after a run
# finishes (keeps the connection open briefly so the client receives the final
# events before the server closes).
_POLL_INTERVAL = 0.3
_FINISH_GRACE = 3.0
_MAX_IDLE = 120.0
_ALLOWED_DEMO_SCENARIOS = {
    "agent-loop",
    "fullstack",
    "promotion-chain",
    "promotion-chain-pass",
    "refund-guard",
    "refund-guard-pass",
    "release-guard",
    "release-guard-pass",
}


class LiveServer(ThreadingHTTPServer):
    def __init__(self, host: str, port: int, run_root: Path, dist_dir: Path | None) -> None:
        self.run_root = Path(run_root)
        self.dist_dir = Path(dist_dir) if dist_dir else DEFAULT_FRONTEND_DIST
        self.shutdown_evt = threading.Event()
        self.active_demo_runs: set[str] = set()
        self.demo_lock = threading.Lock()
        self.demo_root = self.run_root.parent / "live-demos"
        super().__init__((host, port), _Handler)

    def start_demo(self, scenario: str) -> str:
        if scenario not in _ALLOWED_DEMO_SCENARIOS:
            raise ValueError("unsupported synthetic demo scenario")
        safe_scenario = re.sub(r"[^a-z0-9-]", "-", scenario)
        run_id = f"live-{safe_scenario}-{int(time.time() * 1000)}"
        with self.demo_lock:
            if self.active_demo_runs:
                raise RuntimeError("another synthetic demo is already running")
            self.active_demo_runs.add(run_id)
        thread = threading.Thread(target=self._execute_demo, args=(scenario, run_id), daemon=True)
        thread.start()
        return run_id

    def _execute_demo(self, scenario: str, run_id: str) -> None:
        try:
            from .demo.fullstack import DemoRunConfig, run_agent_loop_demo, run_fullstack_demo
            from .demo.investigation import run_investigation_demo
            from .demo.release_guard import run_release_guard_demo
            from .env import load_env_file

            load_env_file(REPO_ROOT / ".env")
            config = DemoRunConfig(
                demo_root=self.demo_root,
                planner_mode="agent-strict",
                allow_temp_test_code=True,
                runs_root=self.run_root,
                run_id=run_id,
            )
            if scenario == "agent-loop":
                run_agent_loop_demo(config)
            elif scenario == "fullstack":
                run_fullstack_demo(config)
            elif scenario in {"release-guard", "release-guard-pass"}:
                run_release_guard_demo(config, repaired=scenario.endswith("-pass"))
            else:
                run_investigation_demo(config, scenario)
        except Exception as exc:  # keep the live UI informed instead of losing the background error
            from .events import EventSink
            from .redaction import redact_secrets

            sink = EventSink(self.run_root / run_id / "events.jsonl")
            sink.verdict(
                "needs-follow-up",
                "unknown",
                "execution-error",
                redact_secrets(f"Synthetic demo execution failed: {type(exc).__name__}: {exc}"),
            )
            sink.done()
        finally:
            with self.demo_lock:
                self.active_demo_runs.discard(run_id)

    def serve_forever(self, poll_interval: float = 0.5) -> None:  # type: ignore[override]
        try:
            super().serve_forever(poll_interval)
        finally:
            self.shutdown_evt.set()


def serve_live(
    run_id: str,
    host: str = "0.0.0.0",
    port: int = 8789,
    run_root: Path | None = None,
    dist_dir: Path | None = None,
) -> LiveServer:
    """Start the live dashboard server (non-blocking) and return it."""
    root = Path(run_root) if run_root else Path("runs")
    server = LiveServer(host, port, root, dist_dir)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # --- routing -----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        if path == "/api/capabilities":
            self._send_json(
                200,
                {
                    "can_execute": True,
                    "mode": "local-live-server",
                    "scenarios": sorted(_ALLOWED_DEMO_SCENARIOS),
                    "busy": bool(self.server.active_demo_runs),
                },
            )
        elif path == "/api/replays":
            self._serve_replay_catalog()
        elif path == "/api/events":
            self._stream_events(qs)
        elif path == "/api/run.json":
            self._serve_run_file(qs, "run.json", "application/json")
        elif path == "/api/report.html":
            self._serve_run_file(qs, "report.html", "text/html")
        elif path.startswith("/files/"):
            self._serve_run_path(qs, path[len("/files/"):])
        elif path.startswith("/assets/"):
            self._serve_asset(path)
        else:
            self._serve_index()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/demo/start":
            self.send_error(404, "not found")
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "invalid content length")
            return
        if size <= 0 or size > 4096:
            self.send_error(400, "invalid request body")
            return
        try:
            body = json.loads(self.rfile.read(size))
        except json.JSONDecodeError:
            self.send_error(400, "invalid JSON")
            return
        scenario = str(body.get("scenario") or "") if isinstance(body, dict) else ""
        try:
            run_id = self.server.start_demo(scenario)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except RuntimeError as exc:
            self._send_json(409, {"error": str(exc)})
            return
        self._send_json(202, {"run_id": run_id, "events_url": f"/api/events?run_id={run_id}"})

    def log_message(self, *args) -> None:  # silence default stderr logging
        return

    # --- SSE ---------------------------------------------------------------
    def _stream_events(self, qs: dict) -> None:
        run_id = (qs.get("run_id") or [None])[0]
        if not run_id:
            self.send_error(400, "missing run_id")
            return
        events_file = self.server.run_root / run_id / "events.jsonl"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.wfile.write(b": connected\n\n")
        self.wfile.flush()

        offset = 0
        buffer = ""
        idle = 0.0
        finished = False
        done_at = 0.0
        start = time.time()
        while not self.server.shutdown_evt.is_set():
            try:
                if events_file.exists():
                    if offset > events_file.stat().st_size:
                        offset = 0
                    with events_file.open("rb") as handle:
                        handle.seek(offset)
                        raw = handle.read()
                        offset = handle.tell()
                    buffer += raw.decode("utf-8", errors="replace")
                    *complete, buffer = buffer.split("\n")
                    for raw_line in complete:
                        line = raw_line.rstrip("\r")
                        if not line.strip():
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        payload = json.dumps(event, ensure_ascii=False)
                        try:
                            self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        if event.get("type") == "done":
                            finished = True
                    if finished and done_at == 0.0:
                        done_at = time.time()
            except (BrokenPipeError, ConnectionResetError):
                return
            if finished and time.time() - done_at >= _FINISH_GRACE:
                # Run is complete: close the stream so one-shot clients
                # (curl, replay tooling) receive EOF instead of hanging on a
                # keep-alive connection. Browsers using EventSource already
                # closed on the `done` event.
                self.close_connection = True
                return
            idle += _POLL_INTERVAL
            if idle >= 15.0:
                try:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
                idle = 0.0
            if not events_file.exists() and (time.time() - start) > _MAX_IDLE:
                self.close_connection = True
                return
            time.sleep(_POLL_INTERVAL)

    # --- file serving -----------------------------------------------------
    def _run_dir(self, qs: dict) -> Path | None:
        run_id = (qs.get("run_id") or [None])[0]
        if not run_id:
            return None
        return self.server.run_root / run_id

    def _serve_run_file(self, qs: dict, name: str, content_type: str) -> None:
        run_dir = self._run_dir(qs)
        if run_dir is None:
            self.send_error(400, "missing run_id")
            return
        target = run_dir / name
        if not target.exists():
            self.send_error(404, f"{name} not found")
            return
        self._send_file(target, content_type)

    def _serve_replay_catalog(self) -> None:
        target = self.server.run_root / "replays.json"
        if not target.exists():
            self._send_json(200, {"default_task_id": "task-45", "items": []})
            return
        self._send_file(target, "application/json")

    def _serve_run_path(self, qs: dict, rel: str) -> None:
        run_dir = self._run_dir(qs)
        if run_dir is None:
            self.send_error(400, "missing run_id")
            return
        target = (run_dir / rel).resolve()
        if not str(target).startswith(str(run_dir.resolve())):
            self.send_error(403, "forbidden")
            return
        if not target.exists() or target.is_dir():
            self.send_error(404, "not found")
            return
        ctype, _ = mimetypes.guess_type(target.name)
        self._send_file(target, ctype or "application/octet-stream")

    def _serve_asset(self, path: str) -> None:
        if not self.server.dist_dir.exists():
            self.send_error(404, "frontend not built")
            return
        rel = path.lstrip("/")
        target = (self.server.dist_dir / rel).resolve()
        if not str(target).startswith(str(self.server.dist_dir.resolve())):
            self.send_error(403, "forbidden")
            return
        if not target.exists() or target.is_dir():
            self.send_error(404, "not found")
            return
        ctype, _ = mimetypes.guess_type(target.name)
        self._send_file(target, ctype or "application/octet-stream")

    def _serve_index(self) -> None:
        index = self.server.dist_dir / "index.html"
        if index.exists():
            self._send_file(index, "text/html")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body style='font-family:sans-serif'>"
            b"<h1>AI Test Officer Live Dashboard</h1>"
            b"<p>The React frontend has not been built yet. Run <code>npm run build</code> "
            b"in <code>frontend/</code>, then open this page again.</p>"
            b"<p>You can still verify the event stream with:"
            b"<br><code>curl -N 'http://localhost:8789/api/events?run_id=&lt;id&gt;'</code></p>"
            b"</body></html>"
        )

    def _send_file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)
