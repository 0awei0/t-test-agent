from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelProviderConfig:
    api_key: str | None
    model: str
    base_url: str | None
    openai_api: str | None
    disable_tracing: bool

    @property
    def available(self) -> bool:
        return bool(self.api_key)


def load_env_file(path: Path | str | None = None) -> dict[str, str]:
    env_path = Path(path or ".env")
    if not env_path.exists():
        return {}

    loaded: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = _strip_quotes(value.strip())
        loaded[key] = value
        os.environ.setdefault(key, value)
    return loaded


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def model_provider_from_env() -> ModelProviderConfig:
    api_key = _env_first("AI_TEST_OFFICER_API_KEY", "OPENAI_API_KEY", "ARK_API_KEY")
    base_url = _base_url()
    return ModelProviderConfig(
        api_key=api_key,
        model=_model_name(),
        base_url=base_url,
        openai_api=os.getenv("AI_TEST_OFFICER_OPENAI_API") or ("chat_completions" if base_url else None),
        disable_tracing=_truthy(os.getenv("AI_TEST_OFFICER_DISABLE_TRACING")) or bool(base_url),
    )


def configure_agents_sdk(config: ModelProviderConfig) -> bool:
    if not config.api_key:
        return False
    try:
        from agents import (
            set_default_openai_api,
            set_default_openai_client,
            set_default_openai_key,
            set_tracing_disabled,
        )
        from openai import AsyncOpenAI
    except ImportError:
        return False

    if config.disable_tracing:
        set_tracing_disabled(True)

    if config.base_url:
        set_default_openai_client(
            AsyncOpenAI(base_url=config.base_url, api_key=config.api_key),
            use_for_tracing=False,
        )
    else:
        set_default_openai_key(config.api_key, use_for_tracing=not config.disable_tracing)

    if config.openai_api:
        set_default_openai_api(config.openai_api)
    return True


def _model_name() -> str:
    configured = os.getenv("AI_TEST_OFFICER_MODEL")
    if configured:
        return configured
    if os.getenv("ARK_API_KEY"):
        return "doubao-seed-2-1-turbo-260628"
    return "gpt-5.4-mini"


def _base_url() -> str | None:
    configured = _env_first("AI_TEST_OFFICER_BASE_URL", "OPENAI_BASE_URL", "ARK_BASE_URL")
    if configured:
        return configured
    if os.getenv("ARK_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        return "https://ark.cn-beijing.volces.com/api/v3"
    return None


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _truthy(value: str | None) -> bool:
    return bool(value and value.lower() in {"1", "true", "yes", "on"})
