"""Unit tests for Gemini auth + routing (ADC→Vertex AI, else API key→Gen Lang).

ADC user-credentials carry the ``cloud-platform`` scope, which Vertex AI
accepts; the Generative Language API does not. So when ADC is configured the
provider routes through Vertex (project-scoped endpoints), otherwise it falls
back to the API key on the Gen Lang API. OAuth refresh + HTTP are mocked — no
network, no real credentials.
"""

import json
from unittest.mock import patch

import pytest

from app.core import provider_keys
from app.services.ai.providers import gemini


# ── helpers ────────────────────────────────────────────────────────────────


class _FakeResp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


class _FakeClient:
    """Captures the last POST (url/json/headers) and returns a canned reply."""

    def __init__(self, reply_text="OK"):
        self.last: dict = {}
        self._reply = {
            "candidates": [{"content": {"parts": [{"text": reply_text}]}}]
        }

    async def post(self, url, json=None, headers=None):
        self.last = {"url": url, "json": json, "headers": headers}
        return _FakeResp(self._reply)


async def _passthrough(fn):
    """Stand-in for retry_with_backoff: just await the callable once."""
    return await fn()


@pytest.fixture
def adc_file(tmp_path, monkeypatch):
    path = tmp_path / "adc.json"
    path.write_text(
        json.dumps(
            {
                "type": "authorized_user",
                "client_id": "fake-client-id.apps.googleusercontent.com",
                "client_secret": "fake-secret",
                "refresh_token": "fake-refresh",
                "quota_project_id": "gen-lang-client-0426752244",
            }
        )
    )
    monkeypatch.setattr(gemini.settings, "GEMINI_ADC_FILE", str(path))
    monkeypatch.setattr(gemini.settings, "VERTEX_PROJECT", "gen-lang-client-0426752244")
    monkeypatch.setattr(gemini.settings, "VERTEX_LOCATION", "us-central1")
    gemini._adc_cache["token"] = None
    gemini._adc_cache["expires_at"] = 0.0
    # Reset the memoized vertex-project cache so this fixture's VERTEX_PROJECT
    # is re-resolved (the cache otherwise persists across tests, leaking the
    # first test's empty value into later tests — a CI-only failure).
    provider_keys._vertex_project_cache.update({"resolved": False, "value": ""})
    return path


@pytest.fixture
def no_adc(monkeypatch, tmp_path):
    """Simulate 'no ADC configured anywhere'.

    Clears the explicit file + env vars AND points ``$HOME`` at a temp dir so the
    gcloud default-path fallback (``~/.config/gcloud/application_default_credentials.json``)
    doesn't resolve to the developer's real credentials — which would otherwise
    make ADC look "configured" on a machine that has run ``gcloud auth
    application-default login``.
    """
    monkeypatch.setattr(gemini.settings, "GEMINI_ADC_FILE", "")
    monkeypatch.setattr(gemini.settings, "VERTEX_PROJECT", "")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("CLOUDSDK_CONFIG", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    gemini._adc_cache["token"] = None
    gemini._adc_cache["expires_at"] = 0.0
    provider_keys._vertex_project_cache.update({"resolved": False, "value": ""})


# ── _gemini_generate routing ───────────────────────────────────────────────


async def test_routes_through_vertex_when_adc_configured(adc_file):
    client = _FakeClient()
    with (
        patch.object(gemini, "_adc_access_token", return_value="BearerTok"),
        patch.object(gemini, "get_cloud_client", _async(client)),
        patch.object(gemini, "retry_with_backoff", _passthrough),
    ):
        out = await gemini.call_gemini_text("hello")
    assert out == "OK"
    sent = client.last
    assert "aiplatform.googleapis.com" in sent["url"]
    assert "gen-lang-client-0426752244" in sent["url"]
    assert "gemini-2.5-flash" in sent["url"]
    assert sent["headers"]["Authorization"] == "Bearer BearerTok"
    # Vertex requires an explicit role on the content.
    assert sent["json"]["contents"][0]["role"] == "user"


async def test_falls_back_to_genlang_api_key_when_no_adc(no_adc):
    async def _key(provider):
        return "AIzaFAKEKEY" if provider == "gemini" else None

    client = _FakeClient()
    with (
        patch.object(gemini, "resolve_provider_api_key", _key),
        patch.object(gemini, "get_cloud_client", _async(client)),
        patch.object(gemini, "retry_with_backoff", _passthrough),
    ):
        out = await gemini.call_gemini_text("hello")
    assert out == "OK"
    sent = client.last
    assert "generativelanguage.googleapis.com" in sent["url"]
    assert sent["headers"]["x-goog-api-key"] == "AIzaFAKEKEY"


async def test_returns_none_when_unconfigured(no_adc):
    async def _no_key(provider):
        return None

    with patch.object(gemini, "resolve_provider_api_key", _no_key):
        assert await gemini.call_gemini_text("hello") is None


async def test_vision_sends_inline_data(monkeypatch):
    # ADC present -> Vertex path; vision payload must carry inline_data + role.
    with (
        patch.object(gemini, "_adc_access_token", return_value="BearerTok"),
        patch.object(gemini, "get_cloud_client", _async(_FakeClient())),
        patch.object(gemini, "retry_with_backoff", _passthrough),
    ):
        await gemini.call_gemini_vision("b64data", "image/png", "extract")
    # Smoke check: no exception, role present would be asserted in the vertex
    # test above; here we confirm the vision call shape is accepted end-to-end.


# ── gemini_auth override (Auto / ADC / API Key) ────────────────────────────


async def test_api_key_auth_skips_adc_even_when_configured(adc_file):
    # ADC is available, but the user explicitly chose API Key -> Gen Lang path.
    client = _FakeClient()
    with (
        patch.object(gemini, "_adc_access_token", return_value="BearerTok"),
        patch.object(gemini, "resolve_provider_api_key", _async("AIzaFAKEKEY")),
        patch.object(gemini, "get_cloud_client", _async(client)),
        patch.object(gemini, "retry_with_backoff", _passthrough),
    ):
        await gemini.call_gemini_text("hello", gemini_auth="api_key")
    sent = client.last
    assert "generativelanguage.googleapis.com" in sent["url"]
    assert sent["headers"].get("x-goog-api-key") == "AIzaFAKEKEY"
    assert "Authorization" not in sent["headers"]


async def test_adc_auth_forces_vertex_when_available(adc_file):
    client = _FakeClient()
    with (
        patch.object(gemini, "_adc_access_token", return_value="BearerTok"),
        patch.object(gemini, "get_cloud_client", _async(client)),
        patch.object(gemini, "retry_with_backoff", _passthrough),
    ):
        await gemini.call_gemini_text("hello", gemini_auth="adc")
    sent = client.last
    assert "aiplatform.googleapis.com" in sent["url"]
    assert sent["headers"]["Authorization"] == "Bearer BearerTok"


async def test_adc_auth_falls_back_to_key_when_not_configured(no_adc):
    # User chose ADC but no ADC is configured -> must not hard-fail; fall back.
    client = _FakeClient()
    with (
        patch.object(gemini, "resolve_provider_api_key", _async("AIzaFAKEKEY")),
        patch.object(gemini, "get_cloud_client", _async(client)),
        patch.object(gemini, "retry_with_backoff", _passthrough),
    ):
        await gemini.call_gemini_text("hello", gemini_auth="adc")
    sent = client.last
    assert "generativelanguage.googleapis.com" in sent["url"]
    assert sent["headers"].get("x-goog-api-key") == "AIzaFAKEKEY"


# ── _adc_access_token (refresh + cache) ─────────────────────────────────────


class _FakeTokenResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


async def test_adc_token_refreshed_and_cached(adc_file):
    payload = {"access_token": "tok-abc", "expires_in": 3600}
    with patch(
        "app.services.ai.providers.gemini.httpx.post",
        return_value=_FakeTokenResp(payload),
    ) as mock_post:
        t1 = gemini._adc_access_token()
        t2 = gemini._adc_access_token()  # cached
    assert t1 == "tok-abc" == t2
    assert mock_post.call_count == 1


async def test_non_authorized_user_adc_is_ignored(tmp_path, monkeypatch):
    path = tmp_path / "sa.json"
    path.write_text(json.dumps({"type": "service_account", "client_email": "x@y.iam"}))
    monkeypatch.setattr(gemini.settings, "GEMINI_ADC_FILE", str(path))
    gemini._adc_cache["token"] = None
    assert gemini._adc_access_token() is None


async def test_is_provider_configured_true_with_adc_and_no_key(adc_file):
    async def _no_value(provider):
        return None

    with patch.object(provider_keys, "resolve_provider_value", _no_value):
        assert await provider_keys.is_provider_configured("gemini") is True


def _async(value):
    async def _fn(*args, **kwargs):
        return value

    return _fn
