"""LLM client — OpenAI-compatible API adapter.

Design goals:
  - Provider, model, API key, and base URL all from env vars.
  - Swappable by changing LLM_PROVIDER without any code changes.
  - A single `chat_complete()` method covers all use cases in this app.
  - Never swallows errors — LLM failures propagate as LLMError.

Supported LLM_PROVIDER values:
  openai        — api.openai.com  (default)
  openrouter    — openrouter.ai   (pass LLM_BASE_URL=https://openrouter.ai/api/v1)
  compatible    — any OpenAI-compatible endpoint (set LLM_BASE_URL)

All three use the openai Python library with an optional custom base_url.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import NamedTuple

from landy.config import settings
from landy.logging_setup import logger


class LLMError(Exception):
    """Raised when an LLM call fails (network, quota, JSON, etc.)."""


class ChatCompletion(NamedTuple):
    content: str
    input_tokens: int
    output_tokens: int
    model: str


class LLMClient(ABC):
    """Abstract LLM client — one method, swappable impl."""

    @abstractmethod
    def chat_complete(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        max_tokens: int = 1500,
        json_mode: bool = True,
    ) -> ChatCompletion:
        """Send a chat completion request.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            model: Override the default model for this call.
            max_tokens: Max completion tokens.
            json_mode: If True, request JSON-only output (response_format).
                       Some endpoints do not support this; falls back silently.

        Returns:
            ChatCompletion with content, token counts, and actual model name.

        Raises:
            LLMError: On any provider error or unexpected response shape.
        """


class OpenAICompatibleClient(LLMClient):
    """OpenAI-compatible client (covers OpenAI, OpenRouter, local endpoints)."""

    def __init__(self) -> None:
        try:
            from openai import OpenAI  # type: ignore[import]
        except ImportError as exc:
            raise LLMError(
                "The 'openai' package is not installed. "
                "Run: pip install openai>=1.54.0"
            ) from exc

        if not settings.llm_api_key:
            raise LLMError(
                "LLM_API_KEY is not set. "
                "Set it to your provider's API key to enable analysis."
            )

        kwargs: dict = {"api_key": settings.llm_api_key}
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url

        self._client = OpenAI(**kwargs)
        self._default_model = settings.llm_model
        logger.info(
            "llm_client_init",
            provider=settings.llm_provider,
            model=self._default_model,
            base_url=settings.llm_base_url or "(default)",
        )

    def chat_complete(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        max_tokens: int = 1500,
        json_mode: bool = True,
    ) -> ChatCompletion:
        m = model or self._default_model
        try:
            kwargs: dict = {
                "model": m,
                "messages": messages,
                "max_completion_tokens": max_tokens,
                # temperature is fixed at 1 for gpt-5 series; older models accept it
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = self._client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            content = choice.message.content or ""
            usage = response.usage
            return ChatCompletion(
                content=content,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                model=response.model,
            )
        except Exception as exc:
            raise LLMError(f"LLM API call failed: {exc}") from exc


# ── Factory ───────────────────────────────────────────────────────────────────

_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Return the singleton LLM client (lazy init, fails fast on bad config)."""
    global _client
    if _client is None:
        provider = settings.llm_provider.lower()
        if provider in ("openai", "openrouter", "compatible", "azure_compat"):
            _client = OpenAICompatibleClient()
        else:
            raise LLMError(
                f"Unsupported LLM_PROVIDER: {provider!r}. "
                "Set LLM_PROVIDER=openai (or openrouter / compatible)."
            )
    return _client


def assert_llm_configured() -> None:
    """Fail fast at process startup if no LLM provider is configured.

    Contract analysis is the product's core function, so an unconfigured
    provider is a boot-time error, not something discovered on a user's
    first request. Call this from the API and worker entry points before
    they start serving/polling. Does not make a network call — constructing
    the OpenAI-compatible client only validates config presence.
    """
    get_llm_client()


# ── JSON extraction helper ────────────────────────────────────────────────────

def extract_json(content: str) -> dict:
    """Parse JSON from model response.

    Tries direct parse first, then extracts from markdown code blocks.
    Raises ValueError if no valid JSON found.
    """
    content = content.strip()
    # 1. Direct parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    # 2. Extract from ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", content)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # 3. Find first { ... } block
    match2 = re.search(r"\{[\s\S]+\}", content)
    if match2:
        try:
            return json.loads(match2.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"No valid JSON found in model response: {content[:300]!r}")
