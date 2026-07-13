import json
import tempfile
import unittest
from pathlib import Path

from ai_test_officer.events import EventSink, RunPhase


class EventSinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / "events.jsonl"
        self.sink = EventSink(self.path)

    def _read(self) -> list[dict]:
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_emits_sequence_with_timestamp_and_type(self) -> None:
        self.sink.phase(RunPhase.CHECKOUT, "done")
        self.sink.tool_call("t1", "read_file_diff", "start", input="checkout.py")
        self.sink.tool_call("t1", "read_file_diff", "ok", output="diff text")
        events = self._read()
        self.assertEqual(len(events), 3)
        self.assertEqual([e["type"] for e in events], ["phase", "tool_call", "tool_call"])
        for i, ev in enumerate(events, start=1):
            self.assertEqual(ev["seq"], i)
            self.assertIn("ts", ev)
            self.assertIn("data", ev)

    def test_convenience_helpers_write_expected_fields(self) -> None:
        self.sink.command("c1", "python -m unittest", "fail", category="agent", returncode=1, log_path="logs/c1.log")
        self.sink.evidence("evidence/shot.png", "screenshot", caption="page")
        self.sink.verdict("fail", "high", failure_category="test-failure", summary="boom")
        self.sink.done()
        events = self._read()
        self.assertEqual(events[0]["data"]["returncode"], 1)
        self.assertEqual(events[0]["data"]["log_path"], "logs/c1.log")
        self.assertEqual(events[1]["data"]["kind"], "screenshot")
        self.assertEqual(events[2]["data"]["verdict"], "fail")
        self.assertEqual(events[3]["type"], "done")

    def test_emits_memory_and_isolation_capabilities(self) -> None:
        self.sink.isolation()
        self.sink.memory("structured", 10_000, 3_000, 0.3, 4)

        events = self._read()

        self.assertEqual(events[0]["data"]["source_repo"], "read-only")
        self.assertEqual(events[0]["data"]["remote_mutation"], "disabled")
        self.assertEqual(events[1]["data"]["compression_ratio"], 0.3)
        self.assertEqual(events[1]["data"]["artifact_count"], 4)

    def test_thread_safe_append(self) -> None:
        import threading

        def worker(n: int) -> None:
            for _ in range(n):
                self.sink.phase(RunPhase.PLANNING, "start")

        threads = [threading.Thread(target=worker, args=(20,)) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 80 appends must all be present and parseable.
        self.assertEqual(len(self._read()), 80)
