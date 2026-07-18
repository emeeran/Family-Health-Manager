"""Tests for the AI provider status endpoint.

Focus: the Ollama branch must report availability from the instant ``/api/tags``
check (reachable + model installed), NOT from a generation probe. On CPU-only
inference a generation probe cold-loads the model (~15-20s+) and routinely
exceeded the endpoint's 20s cap, making a healthy Ollama look "down".
"""

import pytest

from app.core import ollama_service

pytestmark = pytest.mark.asyncio

STATUS_PATH = "/api/v1/ai/status"


async def _ollama_provider(providers):
    return next(p for p in providers if p["id"] == "ollama")


async def test_ollama_available_when_reachable_and_model_installed(auth_client, monkeypatch):
    """Reachable server + installed model -> available, with fast response_ms."""
    monkeypatch.setattr(
        "app.core.provider_keys.resolve_provider_value",
        lambda provider: _ret("http://localhost:11434"),
    )
    monkeypatch.setattr(
        "app.core.ollama_service.ollama_status",
        lambda model, url: _ret((True, True)),
    )

    # Guard: a generation probe must never run for the status check.
    async def _no_generate(*a, **k):  # pragma: no cover - asserted not called
        raise AssertionError("status check must not generate via call_ollama_text")

    monkeypatch.setattr("app.services.ai.providers.ollama.call_ollama_text", _no_generate)
    # Neutralise cloud providers so the test is hermetic.
    monkeypatch.setattr("app.routers.ai.is_provider_configured", lambda p: _ret(False))

    resp = await auth_client.get(STATUS_PATH)
    assert resp.status_code == 200
    ollama = await _ollama_provider(resp.json()["providers"])
    assert ollama["available"] is True
    assert "error" not in ollama
    assert ollama["response_ms"] < 5000  # tags check is near-instant, not a model load


async def test_ollama_unavailable_when_model_not_installed(auth_client, monkeypatch):
    monkeypatch.setattr(
        "app.core.provider_keys.resolve_provider_value",
        lambda provider: _ret("http://localhost:11434"),
    )
    monkeypatch.setattr(
        "app.core.ollama_service.ollama_status",
        lambda model, url: _ret((True, False)),
    )
    monkeypatch.setattr("app.routers.ai.is_provider_configured", lambda p: _ret(False))

    resp = await auth_client.get(STATUS_PATH)
    ollama = await _ollama_provider(resp.json()["providers"])
    assert ollama["available"] is False
    assert "not installed" in ollama["error"]


async def test_ollama_unavailable_when_server_unreachable(auth_client, monkeypatch):
    monkeypatch.setattr(
        "app.core.provider_keys.resolve_provider_value",
        lambda provider: _ret("http://localhost:11434"),
    )
    monkeypatch.setattr(
        "app.core.ollama_service.ollama_status",
        lambda model, url: _ret((False, False)),
    )
    monkeypatch.setattr("app.routers.ai.is_provider_configured", lambda p: _ret(False))

    resp = await auth_client.get(STATUS_PATH)
    ollama = await _ollama_provider(resp.json()["providers"])
    assert ollama["available"] is False
    assert "Connection refused" in ollama["error"]


# ---------------------------------------------------------------------------
# Unit test for ollama_status() — the helper behind the status check.
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    """Minimal httpx.AsyncClient stand-in for /api/tags."""

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url):
        raise NotImplementedError  # overridden per-test


def _client_returning(payload, status=200):
    class _C(_FakeClient):
        async def get(self, url):
            return _FakeResp(status, payload)

    return _C


async def test_ollama_status_matches_exact_tag_and_base_name(monkeypatch):
    payload = {"models": [{"name": "medgemma:4b"}, {"name": "qwen3:4b"}]}
    monkeypatch.setattr(ollama_service.httpx, "AsyncClient", _client_returning(payload))

    assert await ollama_service.ollama_status("qwen3:4b") == (True, True)  # exact tag
    assert await ollama_service.ollama_status("medgemma") == (True, True)  # base name
    assert await ollama_service.ollama_status("llama3.2") == (True, False)  # missing
    assert await ollama_service.ollama_status(None) == (True, True)  # presence skipped


async def test_ollama_status_unreachable(monkeypatch):
    class _Down(_FakeClient):
        async def get(self, url):
            raise ollama_service.httpx.ConnectError("refused")

    monkeypatch.setattr(ollama_service.httpx, "AsyncClient", _Down)
    assert await ollama_service.ollama_status("medgemma") == (False, False)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _ret(value):
    """Wrap a plain value so it can be used as an async monkeypatch target."""
    return value
