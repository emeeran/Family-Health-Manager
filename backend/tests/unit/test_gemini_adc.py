"""Unit tests for Gemini Application Default Credentials (ADC) auth.

ADC lets the app authenticate to Gemini with an OAuth Bearer token derived from
a gcloud credentials file, as an alternative to the API key. The OAuth token
endpoint and the credentials file are mocked — no network, no real keys.
"""

import json
from unittest.mock import patch

import pytest

from app.core import provider_keys
from app.services.ai.providers import gemini


@pytest.fixture
def adc_file(tmp_path, monkeypatch):
    """Write a fake authorized_user ADC file and point the setting at it."""
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
    gemini._adc_cache["token"] = None
    gemini._adc_cache["expires_at"] = 0.0
    return path


class _FakeResp:
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
        return_value=_FakeResp(payload),
    ) as mock_post:
        token1 = gemini._adc_access_token()
        token2 = gemini._adc_access_token()  # cached — no second refresh
    assert token1 == "tok-abc"
    assert token2 == "tok-abc"
    assert mock_post.call_count == 1  # token cached until near expiry


async def test_auth_headers_prefer_adc_bearer(adc_file):
    with patch(
        "app.services.ai.providers.gemini.httpx.post",
        return_value=_FakeResp({"access_token": "tok-xyz", "expires_in": 3600}),
    ):
        headers = await gemini._gemini_auth_headers()
    assert headers == {"Authorization": "Bearer tok-xyz"}


async def test_auth_headers_fall_back_to_api_key(monkeypatch):
    # No ADC file, no GOOGLE_APPLICATION_CREDENTIALS.
    monkeypatch.setattr(gemini.settings, "GEMINI_ADC_FILE", "")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    gemini._adc_cache["token"] = None

    async def _fake_key(provider):
        return "AIzaFAKEKEY" if provider == "gemini" else None

    monkeypatch.setattr(gemini, "resolve_provider_api_key", _fake_key)
    headers = await gemini._gemini_auth_headers()
    assert headers == {"x-goog-api-key": "AIzaFAKEKEY"}


async def test_auth_headers_none_when_unconfigured(monkeypatch):
    monkeypatch.setattr(gemini.settings, "GEMINI_ADC_FILE", "")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    gemini._adc_cache["token"] = None

    async def _no_key(provider):
        return None

    monkeypatch.setattr(gemini, "resolve_provider_api_key", _no_key)
    assert await gemini._gemini_auth_headers() is None


async def test_adc_refresh_failure_falls_back_to_key(adc_file, monkeypatch):
    # OAuth endpoint errors → ADC returns None → API key used instead.
    class _Boom:
        def raise_for_status(self):
            raise RuntimeError("oauth down")

        def json(self):
            return {}

    with patch("app.services.ai.providers.gemini.httpx.post", return_value=_Boom()):
        async def _fake_key(provider):
            return "AIzaFALLBACK"

        monkeypatch.setattr(gemini, "resolve_provider_api_key", _fake_key)
        headers = await gemini._gemini_auth_headers()
    assert headers == {"x-goog-api-key": "AIzaFALLBACK"}


async def test_is_provider_configured_true_with_adc_and_no_key(adc_file):
    async def _no_value(provider):
        return None

    with patch.object(provider_keys, "resolve_provider_value", _no_value):
        assert await provider_keys.is_provider_configured("gemini") is True


async def test_non_authorized_user_adc_is_ignored(tmp_path, monkeypatch):
    # Service-account style creds aren't supported by the manual refresh path.
    path = tmp_path / "sa.json"
    path.write_text(json.dumps({"type": "service_account", "client_email": "x@y.iam"}))
    monkeypatch.setattr(gemini.settings, "GEMINI_ADC_FILE", str(path))
    gemini._adc_cache["token"] = None
    assert gemini._adc_access_token() is None
