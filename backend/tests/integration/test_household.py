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
