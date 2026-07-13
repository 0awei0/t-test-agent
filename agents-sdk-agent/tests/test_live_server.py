import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from ai_test_officer.live_server import LiveServer


def _write_events(run_dir: Path, events: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n"
    (run_dir / "events.jsonl").write_text(lines, encoding="utf-8")


def _collect_sse(host: str, port: int, run_id: str, timeout: float = 8.0) -> list[dict]:
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    conn.request("GET", f"/api/events?run_id={run_id}")
    resp = conn.getresponse()
    body = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        chunk = resp.read(1)
        if not chunk:
            break
        body += chunk
        if b"done" in body and b"\n\n" in body.split(b"data:")[-1]:
            # crude stop once 'done' event delivered
            if b'"type": "done"' in body or b'"type":"done"' in body:
                break
    conn.close()
    events = []
    for line in body.decode("utf-8").splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


class LiveServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.run_root = self.tmp / "runs"
        self.run_id = "srv-test"
        self.run_dir = self.run_root / self.run_id
        events = [
            {"seq": 1, "ts": 1.0, "type": "phase", "data": {"phase": "checkout", "status": "done"}},
            {"seq": 2, "ts": 1.1, "type": "command", "data": {"id": "c1", "command": "pytest", "status": "start"}},
            {"seq": 3, "ts": 1.2, "type": "command", "data": {"id": "c1", "command": "pytest", "status": "fail", "returncode": 1, "log_path": "logs/c1.log"}},
            {"seq": 4, "ts": 1.3, "type": "verdict", "data": {"verdict": "fail", "risk": "high", "failure_category": "test-failure", "summary": "x"}},
            {"seq": 5, "ts": 1.4, "type": "done", "data": {}},
        ]
        _write_events(self.run_dir, events)
        (self.run_dir / "logs").mkdir()
        (self.run_dir / "logs" / "c1.log").write_text("failure", encoding="utf-8")
        (self.run_dir / "run.json").write_text(json.dumps({"verdict": "fail"}), encoding="utf-8")
        self.server = LiveServer("127.0.0.1", 0, self.run_root, None)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown_evt.set()
        self.server.shutdown()
        self.server.server_close()

    def test_sse_streams_full_history_and_closes(self) -> None:
        events = _collect_sse("127.0.0.1", self.port, self.run_id)
        types = [e["type"] for e in events]
        self.assertEqual(types[:3], ["phase", "command", "command"])
        self.assertIn("verdict", types)
        self.assertIn("done", types)

    def test_run_json_route(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", f"/api/run.json?run_id={self.run_id}")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertEqual(json.loads(resp.read())["verdict"], "fail")
        conn.close()

    def test_run_json_missing(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/api/run.json?run_id=does-not-exist")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 404)
        conn.close()

    def test_files_route_serves_log(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", f"/files/logs/c1.log?run_id={self.run_id}")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertIn(b"failure", resp.read())
        conn.close()


if __name__ == "__main__":
    unittest.main()
