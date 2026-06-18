"""Unit tests for the provider-key resolver.

Covers DB-wins / .env-fallback resolution, failure fallback, and the TTL cache
+ invalidation. No database is touched — ``_load_from_db`` and the env fallback
are monkeypatched.
"""
from unittest.mock import AsyncMock

import pytest

from app.core import provider_keys
from app.core.provider_keys import invalidate_provider_cache, resolve_provider_value

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
