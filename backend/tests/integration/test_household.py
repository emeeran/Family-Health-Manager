"""Integration tests for household endpoints."""

import pytest

pytestmark = pytest.mark.asyncio


async def test_get_household(auth_client):
    """Get household returns household info."""
    resp = await auth_client.get("/api/v1/household")
    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body


async def test_update_household(auth_client):
    """Update household name."""
    resp = await auth_client.put("/api/v1/household", json={"name": "My Family"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "My Family"


async def test_settings_update_preserves_provider_models(auth_client):
    """Toggling a feature must not wipe saved AI provider model choices.

    The UI's FeatureSettings payload omits ``ai_providers``; the settings save
    must preserve the previously-saved provider models (regression guard).
    """
    # 1. Save a custom Gemini model via the provider-config endpoint.
    resp = await auth_client.put(
        "/api/v1/household/ai-provider-config",
        json={
            "providers": [
                {"id": "ollama", "enabled": True, "model": "medgemma"},
                {"id": "gemini", "enabled": True, "model": "gemini-2.5-pro"},
            ],
            "primary_provider": "local",
        },
    )
    assert resp.status_code == 200

    # 2. Toggle a feature, sending FeatureSettings WITHOUT ai_providers (like the UI).
    cur = (await auth_client.get("/api/v1/household/settings")).json()["settings"]
    body = {k: v for k, v in cur.items() if k != "ai_providers"}
    body["ai_features"] = not body.get("ai_features", True)
    resp = await auth_client.put("/api/v1/household/settings", json={"settings": body})
    assert resp.status_code == 200

    # 3. The custom provider model must survive the feature toggle.
    cfg = (await auth_client.get("/api/v1/household/ai-provider-config")).json()["config"]
    gemini = next(p for p in cfg["providers"] if p["id"] == "gemini")
    assert gemini["model"] == "gemini-2.5-pro"
    assert cfg["primary_provider"] == "local"
