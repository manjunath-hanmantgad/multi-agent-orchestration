"""Tests for LLM client provider selection and error handling."""

from __future__ import annotations

import importlib
import sys

import pytest
import dotenv


def import_llm_client_module(monkeypatch: pytest.MonkeyPatch, **env_vars: str) -> object:
    """Import core.llm_client with controlled environment variables."""
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)
    for key in ["LLM_PROVIDER", "LLM_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
        monkeypatch.delenv(key, raising=False)
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    sys.modules.pop("core.llm_client", None)
    return importlib.import_module("core.llm_client")


def test_get_llm_client_uses_anthropic_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anthropic provider builds Anthropic client with model, key, and timeout."""
    module = import_llm_client_module(
        monkeypatch,
        LLM_PROVIDER="anthropic",
        LLM_MODEL="claude-sonnet-4-6",
        ANTHROPIC_API_KEY="test-anthropic-key",
    )

    captured: dict[str, object] = {}

    class FakeAnthropic:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(module, "ChatAnthropic", FakeAnthropic)
    client = module.get_llm_client()

    assert isinstance(client, FakeAnthropic)
    assert captured["model"] == "claude-sonnet-4-6"
    assert captured["anthropic_api_key"] == "test-anthropic-key"
    assert captured["default_request_timeout"] == 30


def test_get_llm_client_uses_openai_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI provider builds OpenAI client with model, key, and timeout."""
    module = import_llm_client_module(
        monkeypatch,
        LLM_PROVIDER="openai",
        LLM_MODEL="gpt-4o-mini",
        OPENAI_API_KEY="test-openai-key",
    )

    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(module, "ChatOpenAI", FakeOpenAI)
    client = module.get_llm_client()

    assert isinstance(client, FakeOpenAI)
    assert captured["model"] == "gpt-4o-mini"
    assert captured["openai_api_key"] == "test-openai-key"
    assert captured["request_timeout"] == 30


def test_openai_without_llm_model_uses_openai_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI provider uses its own default model when LLM_MODEL is unset."""
    module = import_llm_client_module(
        monkeypatch,
        LLM_PROVIDER="openai",
        OPENAI_API_KEY="test-openai-key",
    )

    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(module, "ChatOpenAI", FakeOpenAI)
    module.get_llm_client()

    assert captured["model"] == "gpt-4o-mini"


def test_missing_api_key_raises_at_import_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing provider API key fails when module imports, not on function call."""
    with pytest.raises(RuntimeError, match="Missing required environment variable: ANTHROPIC_API_KEY"):
        import_llm_client_module(
            monkeypatch,
            LLM_PROVIDER="anthropic",
            LLM_MODEL="claude-sonnet-4-6",
        )


def test_unsupported_provider_raises_at_import_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unsupported provider value raises a clear import-time configuration error."""
    with pytest.raises(RuntimeError, match="Unsupported LLM_PROVIDER"):
        import_llm_client_module(
            monkeypatch,
            LLM_PROVIDER="azure-openai",
            LLM_MODEL="gpt-4o-mini",
            OPENAI_API_KEY="unused",
        )


def test_get_llm_client_wraps_constructor_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider client construction errors are wrapped in LLMClientError."""
    module = import_llm_client_module(
        monkeypatch,
        LLM_PROVIDER="openai",
        LLM_MODEL="gpt-4o-mini",
        OPENAI_API_KEY="test-openai-key",
    )

    class BrokenOpenAI:
        def __init__(self, **_: object) -> None:
            raise ValueError("invalid model configuration")

    monkeypatch.setattr(module, "ChatOpenAI", BrokenOpenAI)

    with pytest.raises(module.LLMClientError, match="provider=openai model=gpt-4o-mini"):
        module.get_llm_client()
