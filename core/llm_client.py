"""Unified LLM client factory for supported providers."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o-mini",
}
TIMEOUT_SECONDS = 30


class LLMClientError(RuntimeError):
    """Raised for LLM configuration and client construction failures."""


@dataclass(frozen=True)
class LLMSettings:
    """Resolved settings required to construct the configured LLM client."""

    provider: str
    model: str
    api_key: str


def _require_api_key(provider: str) -> str:
    """Return provider API key or raise a clear configuration error."""
    key_env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
    }
    env_name = key_env_map[provider]
    api_key = os.getenv(env_name)
    if not api_key:
        raise LLMClientError(
            f"Missing required environment variable: {env_name} "
            f"(provider={provider})"
        )
    return api_key


def _load_settings() -> LLMSettings:
    """Load and validate provider configuration from environment variables."""
    load_dotenv()
    provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER).strip().lower()
    if provider not in {"anthropic", "openai"}:
        raise LLMClientError(f"Unsupported LLM_PROVIDER: {provider}")
    model = os.getenv("LLM_MODEL", DEFAULT_MODELS[provider]).strip()
    if not model:
        raise LLMClientError("LLM_MODEL must not be empty")
    api_key = _require_api_key(provider)
    return LLMSettings(provider=provider, model=model, api_key=api_key)


SETTINGS = _load_settings()


def _build_anthropic_client(settings: LLMSettings) -> ChatAnthropic:
    """Construct Anthropic chat client with consistent timeout behavior."""
    model = ChatAnthropic(
        model=settings.model,
        anthropic_api_key=settings.api_key,
        default_request_timeout=TIMEOUT_SECONDS,
    )
    handler = _get_langfuse_handler()
    if handler is None:
        return model
    callbacks = [handler]
    return model.with_config({"callbacks": callbacks})


def _build_openai_client(settings: LLMSettings) -> ChatOpenAI:
    """Construct OpenAI chat client with consistent timeout behavior."""
    model = ChatOpenAI(
        model=settings.model,
        openai_api_key=settings.api_key,
        request_timeout=TIMEOUT_SECONDS,
    )
    handler = _get_langfuse_handler()
    if handler is None:
        return model
    callbacks = [handler]
    return model.with_config({"callbacks": callbacks})


def _get_langfuse_handler():
    lf_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    lf_secret = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    if not (lf_key and lf_secret):
        return None
    try:
        from langfuse.callback import CallbackHandler

        return CallbackHandler(
            public_key=lf_key,
            secret_key=lf_secret,
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
    except Exception:
        return None


def get_llm_client() -> ChatAnthropic | ChatOpenAI:
    """Return configured LLM client for the active provider."""
    try:
        if SETTINGS.provider == "anthropic":
            return _build_anthropic_client(SETTINGS)
        return _build_openai_client(SETTINGS)
    except (ValidationError, TypeError, ValueError, RuntimeError) as exc:
        message = (
            "Failed to initialize LLM client "
            f"provider={SETTINGS.provider} model={SETTINGS.model} "
            f"error_type={type(exc).__name__}: {exc}"
        )
        raise LLMClientError(message) from exc


def call_llm(
    prompt: str,
    workflow_id: str = "",
    stage: str = "",
    emitter=None,
) -> str:
    """Invoke the LLM synchronously and emit an observability event.

    Returns the response content as a string.
    Raises LLMClientError on failure (observability failure never propagates).
    """
    from core.observability import default_emitter as _default_emitter

    import time

    _emitter = emitter if emitter is not None else _default_emitter
    client = get_llm_client()
    start = time.monotonic()
    try:
        response = client.invoke(prompt)
        return str(getattr(response, "content", ""))
    finally:
        latency_ms = int((time.monotonic() - start) * 1000)
        content = str(getattr(response, "content", "")) if "response" in dir() else ""
        # Extract token counts — normalize Anthropic vs OpenAI field names
        usage = {}
        if "response" in dir() and hasattr(response, "response_metadata"):
            usage = response.response_metadata.get("usage", {})
        input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
        output_tokens = usage.get("output_tokens") or usage.get("completion_tokens") or 0
        _emitter.emit_llm_call(
            workflow_id=workflow_id,
            stage=stage,
            model=SETTINGS.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
