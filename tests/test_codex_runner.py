import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from ai_test_officer.codex_runner import CodexRunner


class CodexRunnerTests(unittest.TestCase):
    def test_run_uses_ephemeral_thread_by_default(self) -> None:
        fake_module, fake_codex = _fake_openai_codex()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(sys.modules, {"openai_codex": fake_module}):
                result = CodexRunner().run("hello", Path(tmp))

        self.assertEqual(result, "ok")
        self.assertEqual(fake_codex.thread_start_calls[0]["ephemeral"], True)
        self.assertEqual(fake_codex.archived_threads, [])

    def test_run_can_keep_and_auto_archive_thread(self) -> None:
        fake_module, fake_codex = _fake_openai_codex()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(sys.modules, {"openai_codex": fake_module}):
                result = CodexRunner(ephemeral=False, auto_archive=True).run("hello", Path(tmp))

        self.assertEqual(result, "ok")
        self.assertEqual(fake_codex.thread_start_calls[0]["ephemeral"], False)
        self.assertEqual(fake_codex.archived_threads, ["thread-1"])

    def test_save_thread_mode_does_not_archive(self) -> None:
        fake_module, fake_codex = _fake_openai_codex()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(sys.modules, {"openai_codex": fake_module}):
                CodexRunner(ephemeral=False, auto_archive=False).run("hello", Path(tmp))

        self.assertEqual(fake_codex.archived_threads, [])


def _fake_openai_codex() -> tuple[types.SimpleNamespace, object]:
    class FakeSandbox:
        read_only = "read_only"
        workspace_write = "workspace_write"
        full_access = "full_access"

    class FakeThread:
        id = "thread-1"

        def run(self, prompt: str) -> object:
            return types.SimpleNamespace(final_response="ok")

    class FakeCodex:
        latest: "FakeCodex"

        def __init__(self) -> None:
            self.thread_start_calls: list[dict[str, object]] = []
            self.archived_threads: list[str] = []
            FakeCodex.latest = self

        def __enter__(self) -> "FakeCodex":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def thread_start(self, **kwargs: object) -> FakeThread:
            self.thread_start_calls.append(kwargs)
            return FakeThread()

        def thread_archive(self, thread_id: str) -> None:
            self.archived_threads.append(thread_id)

    module = types.SimpleNamespace(Codex=FakeCodex, Sandbox=FakeSandbox)
    fake_codex = FakeCodex()

    def codex_factory() -> FakeCodex:
        return fake_codex

    module.Codex = codex_factory
    return module, fake_codex


if __name__ == "__main__":
    unittest.main()
