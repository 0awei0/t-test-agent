import tempfile
import unittest
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

from ai_test_officer.memory import build_agent_summary_prompt, build_run_memory, compact_text
from ai_test_officer.models import ChangedFile, RunRecord


class MemoryTests(unittest.TestCase):
    def test_compact_text_keeps_head_and_tail(self) -> None:
        text = "a" * 50 + "b" * 50

        compacted = compact_text(text, 95)

        self.assertIn("context compacted by structured budget", compacted)
        self.assertTrue(compacted.startswith("a"))
        self.assertTrue(compacted.endswith("b"))
        self.assertLessEqual(len(compacted), 95)

    def test_build_agent_summary_prompt_has_bounded_content(self) -> None:
        record = RunRecord(
            run_id="memory-run",
            task="Analyze",
            source_repo=Path("/source"),
            workspace_repo=Path("/workspace"),
            run_dir=Path("/runs/memory-run"),
            git_range="base..head",
            changed_files=[ChangedFile("M", "checkout.py")],
            diff_text="x" * 1000,
            allow_temp_test_code=False,
        )

        prompt = build_agent_summary_prompt(record)

        self.assertIn("checkout.py", prompt)
        self.assertIn("Verdict:", prompt)
        self.assertNotIn("x" * 100, prompt)

    def test_build_run_memory_keeps_artifact_paths_not_raw_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "memory-run"
            context_dir = run_dir / "context"
            (context_dir / "diffs").mkdir(parents=True)
            diff_path = context_dir / "diffs" / "checkout.py.diff"
            diff_path.write_text("SECRET_DIFF_" + "x" * 500, encoding="utf-8")
            diff_index = context_dir / "diff-index.json"
            diff_index.write_text('[{"path":"checkout.py","artifact":"diffs/checkout.py.diff"}]', encoding="utf-8")
            (context_dir / "changed-files.json").write_text("[]", encoding="utf-8")
            record = RunRecord(
                run_id="memory-run",
                task="Analyze",
                source_repo=Path("/source"),
                workspace_repo=Path("/workspace"),
                run_dir=run_dir,
                git_range="base..head",
                changed_files=[ChangedFile("M", "checkout.py")],
                diff_text="SECRET_DIFF_" + "x" * 500,
                allow_temp_test_code=False,
                context_dir=context_dir,
                diff_index_path=diff_index,
                context_summary="summary",
            )

            memory = build_run_memory(record, mode="structured")

            rendered = memory.summary_path.read_text(encoding="utf-8") if memory.summary_path else ""
            self.assertEqual(memory.status, "built")
            self.assertIn("context/diffs/checkout.py.diff", rendered)
            self.assertIn("do not use final head-only truncation", rendered)
            self.assertNotIn("SECRET_DIFF_", rendered)
            self.assertIn(diff_path, memory.artifact_paths)

    def test_build_run_memory_model_mode_uses_model_summary_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "memory-run"
            context_dir = run_dir / "context"
            context_dir.mkdir(parents=True)
            diff_index = context_dir / "diff-index.json"
            diff_index.write_text("[]", encoding="utf-8")
            record = RunRecord(
                run_id="memory-run",
                task="Analyze",
                source_repo=Path("/source"),
                workspace_repo=Path("/workspace"),
                run_dir=run_dir,
                git_range="base..head",
                changed_files=[ChangedFile("M", "checkout.py")],
                diff_text="x" * 1000,
                allow_temp_test_code=False,
                context_dir=context_dir,
                diff_index_path=diff_index,
                context_summary="raw context should be summarized",
            )

            with _fake_agents_modules(), patch.dict(
                os.environ,
                {"ARK_API_KEY": "ark", "AI_TEST_OFFICER_MODEL": "doubao-test"},
                clear=True,
            ):
                memory = build_run_memory(record, mode="model")

            self.assertTrue(memory.used_model)
            self.assertEqual(memory.status, "built")
            assert memory.summary_path is not None
            self.assertEqual(memory.summary_path.read_text(encoding="utf-8"), "model structured summary")

def _fake_agents_modules():
    class FakeAgent:
        def __init__(self, *, name, instructions, model):
            self.name = name
            self.instructions = instructions
            self.model = model

    class FakeRunner:
        @staticmethod
        def run_sync(agent, prompt):
            return types.SimpleNamespace(final_output="model structured summary")

    class FakeAsyncOpenAI:
        def __init__(self, *, base_url, api_key):
            self.base_url = base_url
            self.api_key = api_key

    fake_agents = types.SimpleNamespace(
        Agent=FakeAgent,
        Runner=FakeRunner,
        set_default_openai_api=lambda api: None,
        set_default_openai_client=lambda client, use_for_tracing=True: None,
        set_default_openai_key=lambda key, use_for_tracing=True: None,
        set_tracing_disabled=lambda disabled: None,
    )
    fake_openai = types.SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI)
    return patch.dict(sys.modules, {"agents": fake_agents, "openai": fake_openai})


if __name__ == "__main__":
    unittest.main()
