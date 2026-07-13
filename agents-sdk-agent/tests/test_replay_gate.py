import json
import tempfile
import unittest
from pathlib import Path

from ai_test_officer.demo.replay_catalog import DEFAULT_REPLAY_TASK_ID, REPLAY_SPECS
from ai_test_officer.release_gate import ReleaseGateError
from ai_test_officer.replay_gate import validate_replay_package


class ReplayGateTests(unittest.TestCase):
    def test_accepts_complete_agent_replay_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest, runs_root, public_root = self._package(Path(tmp))
            validate_replay_package(manifest, runs_root, public_root)

    def test_rejects_missing_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest, runs_root, public_root = self._package(Path(tmp))
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["items"].pop()
            manifest.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ReleaseGateError, "unexpected replay count"):
                validate_replay_package(manifest, runs_root, public_root)

    def test_rejects_public_local_path_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest, runs_root, public_root = self._package(Path(tmp))
            report = public_root / "replays" / DEFAULT_REPLAY_TASK_ID / "report.html"
            report.write_text("<p>/data/workspace/private</p>", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseGateError, "forbidden content"):
                validate_replay_package(manifest, runs_root, public_root)

    def _package(self, root: Path) -> tuple[Path, Path, Path]:
        runs_root = root / "runs"
        public_root = root / "public"
        items = []
        for spec in REPLAY_SPECS:
            run_dir = runs_root / spec.task_id
            replay_dir = public_root / "replays" / spec.task_id
            run_dir.mkdir(parents=True)
            replay_dir.mkdir(parents=True)
            run = {
                "run_id": spec.task_id,
                "verdict": spec.expected_verdict,
                "risk": spec.expected_risk,
                "commands": [{"command": "python -m unittest"}],
                "summary": "Decision ready.",
                "planner_mode": "agent-strict",
                "required_tool_check": {"passed": True, "missing": []},
                "agent_turns": [{"turn": 1}],
                "agent_final_output": "Decision ready.",
            }
            (run_dir / "run.json").write_text(json.dumps(run), encoding="utf-8")
            event_types = {"isolation", "tool_call", "verdict", "done"}
            if spec.task_id == DEFAULT_REPLAY_TASK_ID:
                event_types.update({"context", "planner", "command", "evidence", "memory"})
            events = "\n".join(
                json.dumps({"seq": index, "type": event_type, "data": {}})
                for index, event_type in enumerate(sorted(event_types), 1)
            )
            (run_dir / "events.jsonl").write_text(events + "\n", encoding="utf-8")
            public_event_types = set(event_types) | {"provenance"}
            if spec.task_id == DEFAULT_REPLAY_TASK_ID:
                public_event_types.add("adaptation")
            if spec.task_id == "task-53":
                public_event_types.add("safety_check")
            public_events = "\n".join(
                json.dumps({"seq": index, "type": event_type, "data": {}})
                for index, event_type in enumerate(sorted(public_event_types), 1)
            )
            (replay_dir / "events.jsonl").write_text(public_events + "\n", encoding="utf-8")
            (replay_dir / "report.html").write_text("<p>safe report</p>", encoding="utf-8")
            items.append(
                {
                    "task_id": spec.task_id,
                    "run_id": spec.task_id,
                    "scenario": spec.scenario,
                    "tapd_id": spec.tapd_id,
                    "mr_iid": spec.mr_iid,
                    "expected_verdict": spec.expected_verdict,
                    "expected_risk": spec.expected_risk,
                    "verdict": spec.expected_verdict,
                    "risk": spec.expected_risk,
                    "tool_calls": 1,
                    "planner_steps": 1,
                    "compression_ratio": 0.5,
                }
            )
        manifest = public_root / "replays" / "manifest.json"
        manifest.write_text(
            json.dumps({"default_task_id": DEFAULT_REPLAY_TASK_ID, "items": items}),
            encoding="utf-8",
        )
        return manifest, runs_root, public_root


if __name__ == "__main__":
    unittest.main()
