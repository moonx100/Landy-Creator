"""Tests for the LLM provider configuration gate (landy.llm / landy.config).

Covers Step 2 of the privacy-path handoff:
  - No Replit AI Integrations fallback remains.
  - get_llm_client() / assert_llm_configured() refuse to proceed with no
    LLM_API_KEY configured, so the API/worker boot-time check actually bites.
  - The interface stays vendor-swappable (LLM_PROVIDER/LLM_BASE_URL/LLM_MODEL
    are read from settings, never hardcoded).

Run with:
    python -m pytest tests/test_llm_provider_config.py -v
"""
from __future__ import annotations

import pytest

import landy.llm as llm_mod
from landy.config import Settings


def _settings(**overrides) -> Settings:
    base = {"database_url": "postgresql://u:p@localhost:5432/db"}
    base.update(overrides)
    return Settings(**base)


@pytest.fixture(autouse=True)
def reset_llm_singleton(monkeypatch):
    """get_llm_client() caches a module-level singleton; reset it per test."""
    monkeypatch.setattr(llm_mod, "_client", None)
    yield
    monkeypatch.setattr(llm_mod, "_client", None)


def test_no_replit_ai_integrations_fields_on_settings():
    s = _settings()
    assert not hasattr(s, "ai_integrations_openai_api_key")
    assert not hasattr(s, "ai_integrations_openai_base_url")
    assert not hasattr(s, "effective_llm_api_key")
    assert not hasattr(s, "effective_llm_base_url")


def test_model_default_is_not_a_placeholder():
    s = _settings()
    # The old default ("gpt-5.6-terra") was never a real model id.
    assert s.llm_model != "gpt-5.6-terra"
    assert s.llm_model  # non-empty


def test_get_llm_client_raises_without_api_key(monkeypatch):
    monkeypatch.setattr(llm_mod, "settings", _settings(llm_api_key=""))
    with pytest.raises(llm_mod.LLMError, match="LLM_API_KEY"):
        llm_mod.get_llm_client()


def test_assert_llm_configured_raises_without_api_key(monkeypatch):
    monkeypatch.setattr(llm_mod, "settings", _settings(llm_api_key=""))
    with pytest.raises(llm_mod.LLMError):
        llm_mod.assert_llm_configured()


def test_get_llm_client_succeeds_with_api_key(monkeypatch):
    monkeypatch.setattr(
        llm_mod, "settings", _settings(llm_api_key="sk-test-key", llm_model="gpt-4o")
    )
    client = llm_mod.get_llm_client()
    assert isinstance(client, llm_mod.OpenAICompatibleClient)


def test_unsupported_provider_rejected(monkeypatch):
    monkeypatch.setattr(
        llm_mod, "settings", _settings(llm_api_key="sk-test-key", llm_provider="not-a-real-provider")
    )
    with pytest.raises(llm_mod.LLMError, match="Unsupported LLM_PROVIDER"):
        llm_mod.get_llm_client()


def test_custom_base_url_is_honoured_not_hardcoded(monkeypatch):
    """Vendor-swappable: pointing LLM_BASE_URL elsewhere must actually change
    where the client talks to, proving the endpoint isn't hardcoded."""
    monkeypatch.setattr(
        llm_mod,
        "settings",
        _settings(
            llm_api_key="sk-test-key",
            llm_base_url="https://compatible-endpoint.example.com/v1",
            llm_provider="compatible",
        ),
    )
    client = llm_mod.get_llm_client()
    assert str(client._client.base_url).startswith("https://compatible-endpoint.example.com")
