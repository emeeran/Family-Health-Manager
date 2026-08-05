"""Unit tests for the provider-key resolver.

Covers DB-wins / .env-fallback resolution, failure fallback, and the TTL cache
+ invalidation. No database is touched — ``_load_from_db`` and the env fallback
are monkeypatched.
"""

from unittest.mock import AsyncMock

import pytest

from app.core import provider_keys
from app.core.provider_keys import (
    invalidate_provider_cache,
    normalize_ollama_url,
    ollama_url_block_reason,
    resolve_provider_value,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clear_cache():
    provider_keys._cache.clear()
    yield
    provider_keys._cache.clear()


async def test_db_value_wins_over_env(monkeypatch):
    monkeypatch.setattr(provider_keys, "_load_from_db", AsyncMock(return_value="db-key"))
    monkeypatch.setattr(provider_keys, "_fallback_from_env", lambda _p: "env-key")
    assert await resolve_provider_value("openai") == "db-key"


async def test_falls_back_to_env_when_no_db_value(monkeypatch):
    monkeypatch.setattr(provider_keys, "_load_from_db", AsyncMock(return_value=None))
    monkeypatch.setattr(provider_keys, "_fallback_from_env", lambda _p: "env-key")
    assert await resolve_provider_value("openai") == "env-key"


async def test_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.setattr(provider_keys, "_load_from_db", AsyncMock(return_value=None))
    monkeypatch.setattr(provider_keys, "_fallback_from_env", lambda _p: None)
    assert await resolve_provider_value("openai") is None


async def test_db_failure_falls_back_to_env(monkeypatch):
    async def _boom(_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(provider_keys, "_load_from_db", _boom)
    monkeypatch.setattr(provider_keys, "_fallback_from_env", lambda _p: "env-key")
    # A DB error must never propagate to the caller — it degrades to .env.
    assert await resolve_provider_value("openai") == "env-key"


async def test_cache_hit_avoids_reread(monkeypatch):
    calls = {"n": 0}

    async def _loader(_k):
        calls["n"] += 1
        return f"v{calls['n']}"

    monkeypatch.setattr(provider_keys, "_load_from_db", _loader)
    monkeypatch.setattr(provider_keys, "_fallback_from_env", lambda _p: None)
    assert await resolve_provider_value("openai") == "v1"
    assert await resolve_provider_value("openai") == "v1"  # served from cache
    assert calls["n"] == 1


async def test_invalidation_forces_reread(monkeypatch):
    calls = {"n": 0}

    async def _loader(_k):
        calls["n"] += 1
        return f"v{calls['n']}"

    monkeypatch.setattr(provider_keys, "_load_from_db", _loader)
    monkeypatch.setattr(provider_keys, "_fallback_from_env", lambda _p: None)
    await resolve_provider_value("openai")  # v1, cached
    invalidate_provider_cache("openai")
    assert await resolve_provider_value("openai") == "v2"
    assert calls["n"] == 2


async def test_normalize_ollama_url_prepends_http_when_scheme_missing():
    # The exact regression: "localhost:11434" typed in Settings breaks httpx.
    assert normalize_ollama_url("localhost:11434") == "http://localhost:11434"
    assert normalize_ollama_url("192.168.1.10:11434") == "http://192.168.1.10:11434"


async def test_normalize_ollama_url_preserves_existing_scheme():
    assert normalize_ollama_url("http://localhost:11434") == "http://localhost:11434"
    assert normalize_ollama_url("https://ollama.local:443") == "https://ollama.local:443"


async def test_normalize_ollama_url_trims_whitespace_and_passes_through_empty():
    assert normalize_ollama_url("  localhost:11434  ") == "http://localhost:11434"
    assert normalize_ollama_url("") == ""
    assert normalize_ollama_url(None) is None


async def test_resolve_normalizes_scheme_less_ollama_db_value(monkeypatch):
    """A scheme-less Ollama URL stored in the DB is fixed up at resolve time."""
    monkeypatch.setattr(provider_keys, "_load_from_db", AsyncMock(return_value="localhost:11434"))
    monkeypatch.setattr(provider_keys, "_fallback_from_env", lambda _p: None)
    assert await resolve_provider_value("ollama") == "http://localhost:11434"


async def test_resolve_does_not_touch_api_key_providers(monkeypatch):
    """Only Ollama (a URL) is normalised — API keys must never get http:// prepended."""
    monkeypatch.setattr(provider_keys, "_load_from_db", AsyncMock(return_value="sk-somekey"))
    monkeypatch.setattr(provider_keys, "_fallback_from_env", lambda _p: None)
    assert await resolve_provider_value("openai") == "sk-somekey"


# ── SSRF guard for the admin-configurable Ollama URL ─────────────────────────


async def test_ollama_ssrf_blocks_cloud_metadata():
    """Link-local + known metadata endpoints are blocked (the SSRF prize)."""
    assert normalize_ollama_url("http://169.254.169.254/latest/meta-data/") is None
    assert normalize_ollama_url("169.254.169.254:11434") is None
    assert normalize_ollama_url("http://metadata.google.internal/computeMetadata/") is None
    assert normalize_ollama_url("http://[fd00:ec2::254]/") is None
    assert ollama_url_block_reason("http://169.254.169.254/") == "cloud metadata endpoint"


async def test_ollama_ssrf_allows_localhost_and_lan():
    """Localhost + private LAN ranges stay usable (Ollama on another box is legit)."""
    assert normalize_ollama_url("localhost:11434") == "http://localhost:11434"
    assert normalize_ollama_url("127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert normalize_ollama_url("192.168.1.20:11434") == "http://192.168.1.20:11434"
    assert normalize_ollama_url("10.0.0.5:11434") == "http://10.0.0.5:11434"
    assert normalize_ollama_url("ollama.home.arpa:11434") == "http://ollama.home.arpa:11434"
    assert ollama_url_block_reason("http://192.168.1.20:11434") is None


async def test_ollama_ssrf_blocks_unspecified_address():
    assert normalize_ollama_url("0.0.0.0:11434") is None
    assert ollama_url_block_reason("http://0.0.0.0/") == "unspecified address"
