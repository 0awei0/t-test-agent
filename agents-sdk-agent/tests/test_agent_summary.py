import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_test_officer.agent_summary import summarize_with_agents_sdk
from ai_test_officer.models import RunRecord


class AgentSummaryTests(unittest.TestCase):
    def test_without_model_key_returns_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(summarize_with_agents_sdk(_record()))

    def test_ark_key_configures_chat_completions_client(self) -> None:
        calls: list[tuple[str, object]] = []

        class FakeAgent:
            def __init__(self, *, name: str, instructions: str, model: str) -> None:
                self.name = name
                self.instructions = instructions
                self.model = model

        class FakeRunner:
            @staticmethod
            def run_sync(agent: FakeAgent, prompt: str) -> object:
                calls.append(("run", (agent.model, "Changed files:" in prompt)))
                return types.SimpleNamespace(final_output=f"summary from {agent.model}")

        class FakeAsyncOpenAI:
            def __init__(self, *, base_url: str, api_key: str) -> None:
                calls.append(("client", (base_url, bool(api_key))))

        fake_agents = types.SimpleNamespace(
            Agent=FakeAgent,
            Runner=FakeRunner,
            set_default_openai_api=lambda api: calls.append(("api", api)),
            set_default_openai_client=lambda client, use_for_tracing=True: calls.append(
                ("default_client", use_for_tracing)
            ),
            set_default_openai_key=lambda key, use_for_tracing=True: calls.append(("default_key", use_for_tracing)),
            set_tracing_disabled=lambda disabled: calls.append(("tracing", disabled)),
        )
        fake_openai = types.SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI)

        with (
            patch.dict(
                os.environ,
                {
                    "ARK_API_KEY": "ark-test-key",
                    "AI_TEST_OFFICER_MODEL": "doubao-seed-2-1-turbo-260628",
                },
                clear=True,
            ),
            patch.dict(sys.modules, {"agents": fake_agents, "openai": fake_openai}),
        ):
            summary = summarize_with_agents_sdk(_record())

        self.assertEqual(summary, "summary from doubao-seed-2-1-turbo-260628")
        self.assertIn(("client", ("https://ark.cn-beijing.volces.com/api/v3", True)), calls)
        self.assertIn(("api", "chat_completions"), calls)
        self.assertIn(("tracing", True), calls)
        self.assertIn(("default_client", False), calls)


def _record() -> RunRecord:
    return RunRecord(
        run_id="unit-run",
        task="Analyze change",
        source_repo=Path(__file__),
        workspace_repo=Path(__file__),
        run_dir=Path(__file__).parent,
        git_range="HEAD~1..HEAD",
        changed_files=[],
        diff_text="",
        allow_temp_test_code=False,
    )


if __name__ == "__main__":
    unittest.main()
