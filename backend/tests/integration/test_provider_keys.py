"""Integration tests for the admin provider-key endpoints.

The first registered user (via ``auth_client``) is the admin; a second
registration is role="user" and is used for the 403 cases.
"""

import pytest

from app.core import provider_keys

pytestmark = pytest.mark.asyncio

KEYS_PATH = "/api/v1/system/provider-keys"


async def _non_admin_token(client) -> str:
    """Register + log in a second user, which is auto-assigned role='user'."""
    resp = await client.post(
        "/api/v1/auth/register", json={"username": "regular", "password": "TestP@ss123"}
    )
    assert resp.status_code == 201, resp.text
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "regular", "password": "TestP@ss123"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def test_list_keys_default(auth_client):
    """GET returns all five providers; none stored initially."""
    resp = await auth_client.get(KEYS_PATH)
    assert resp.status_code == 200
    keys = resp.json()["keys"]
    assert {k["provider"] for k in keys} == {"openai", "gemini", "groq", "openrouter", "ollama"}
    assert all(k["is_set"] is False for k in keys)


async def test_put_then_get_masked_never_plaintext(auth_client):
    """PUT stores the key; subsequent GET returns it masked, never plaintext."""
    resp = await auth_client.put(KEYS_PATH, json={"provider": "openai", "value": "sk-test-12345"})
    assert resp.status_code == 200
    assert resp.json()["is_set"] is True
    assert resp.json()["masked"] == "••••2345"

    resp = await auth_client.get(KEYS_PATH)
    openai = next(k for k in resp.json()["keys"] if k["provider"] == "openai")
    assert openai["is_set"] is True
    assert openai["masked"] == "••••2345"
    assert "sk-test-12345" not in resp.text  # plaintext must never leak


async def test_delete_clears_stored_key(auth_client):
    await auth_client.put(KEYS_PATH, json={"provider": "groq", "value": "gsk_abcdef"})
    resp = await auth_client.delete(f"{KEYS_PATH}/groq")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == "groq"

    resp = await auth_client.get(KEYS_PATH)
    groq = next(k for k in resp.json()["keys"] if k["provider"] == "groq")
    assert groq["is_set"] is False


async def test_ollama_url_is_not_masked(auth_client):
    """The Ollama URL is not a secret — it is returned in full."""
    resp = await auth_client.put(
        KEYS_PATH, json={"provider": "ollama", "value": "http://host:11434"}
    )
    assert resp.status_code == 200
    assert resp.json()["is_secret"] is False
    assert resp.json()["masked"] == "http://host:11434"


async def test_import_from_env(auth_client, monkeypatch):
    """Import copies non-empty .env values into the store."""
    monkeypatch.setattr(
        provider_keys, "_fallback_from_env", lambda p: "sk-env-key" if p == "openai" else None
    )
    resp = await auth_client.post(f"{KEYS_PATH}/import-from-env")
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == ["openai"]
    assert set(body["skipped"]) == {"gemini", "groq", "openrouter", "ollama"}

    resp = await auth_client.get(KEYS_PATH)
    openai = next(k for k in resp.json()["keys"] if k["provider"] == "openai")
    assert openai["is_set"] is True


async def test_non_admin_forbidden(auth_client):
    token = await _non_admin_token(auth_client)
    resp = await auth_client.put(
        KEYS_PATH, json={"provider": "openai", "value": "x"}, params={"token": token}
    )
    assert resp.status_code == 403


async def test_invalid_provider_rejected(auth_client):
    resp = await auth_client.put(KEYS_PATH, json={"provider": "evil", "value": "x"})
    assert resp.status_code == 422
