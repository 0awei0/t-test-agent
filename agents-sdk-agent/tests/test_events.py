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

    def test_emits_structured_test_plan_and_live_update(self) -> None:
        self.sink.test_plan(
            summary="覆盖优惠边界和 API 契约",
            items=[
                {
                    "id": "plan-1",
                    "title": "优惠边界单测",
                    "layer": "单元测试",
                    "target": "Coupon Policy",
                    "command": "python -m unittest tests.test_orders -v",
                    "evidence": "命令日志",
                    "adaptive": False,
                }
            ],
        )
        self.sink.plan_update(
            id="plan-1",
            status="failed",
            detail="exit 1",
            command="python -m unittest tests.test_orders -v",
        )

        events = self._read()
        self.assertEqual([event["type"] for event in events], ["test_plan", "plan_update"])
        self.assertEqual(events[0]["data"]["items"][0]["layer"], "单元测试")
        self.assertEqual(events[1]["data"]["status"], "failed")

    def test_emits_memory_and_isolation_capabilities(self) -> None:
        self.sink.isolation()
        self.sink.memory("structured", 10_000, 3_000, 0.3, 4)

        events = self._read()

        self.assertEqual(events[0]["data"]["source_repo"], "read-only")
        self.assertEqual(events[0]["data"]["remote_mutation"], "disabled")
        self.assertEqual(events[1]["data"]["compression_ratio"], 0.3)
        self.assertEqual(events[1]["data"]["artifact_count"], 4)

    def test_emits_provenance_safety_and_adaptation(self) -> None:
        self.sink.provenance(
            run_id="run-1",
            planner_mode="agent-strict",
            strict_tools_passed=True,
            tool_calls=8,
            model_tool_calls=8,
            commands=2,
            generated_tests=1,
            evidence=1,
        )
        self.sink.safety_check(
            action="execute",
            target="git push origin main",
            status="blocked",
            blocked_by="local_safety_policy",
            reason="remote mutation is blocked",
        )
        self.sink.adaptation(kind="failure-driven-test-expansion", status="completed", detail="added test")

        events = self._read()
        self.assertEqual([event["type"] for event in events], ["provenance", "safety_check", "adaptation"])
        self.assertTrue(events[0]["data"]["strict_tools_passed"])
        self.assertEqual(events[1]["data"]["status"], "blocked")

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
