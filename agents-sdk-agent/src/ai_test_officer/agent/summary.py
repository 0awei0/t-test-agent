from __future__ import annotations

import signal
import threading
from contextlib import contextmanager
from collections.abc import Iterator

from ..config import DEFAULT_AGENT_SUMMARY_TIMEOUT_SEC
from ..memory import build_agent_summary_prompt
from ..models import RunRecord
from ..prompts import load_prompt
from .config import configure_agents_sdk, model_provider_from_env


def summarize_with_agents_sdk(record: RunRecord) -> str | None:
    provider = model_provider_from_env()
    if not provider.available:
        return None
    try:
        from agents import Agent, Runner
    except ImportError:
        return None

    if not configure_agents_sdk(provider):
        return None
    prompt = build_agent_summary_prompt(record)
    agent = Agent(
        name="AI Test Officer Reporter",
        instructions=load_prompt("reporter"),
        model=provider.model,
    )
    try:
        with _summary_timeout(DEFAULT_AGENT_SUMMARY_TIMEOUT_SEC):
            result = Runner.run_sync(agent, prompt)
    except Exception:
        return None
    return str(getattr(result, "final_output", result))


@contextmanager
def _summary_timeout(seconds: int) -> Iterator[None]:
    if threading.current_thread() is not threading.main_thread() or seconds <= 0:
        yield
        return

    def handle_timeout(signum, frame):
        raise TimeoutError("Agent summary timed out")

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, handle_timeout)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, previous_timer[0], previous_timer[1])
