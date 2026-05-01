"""Integration tests for providers CRUD."""
import pytest


pytestmark = pytest.mark.asyncio

PROVIDER_PAYLOAD = {
    "name": "Dr. House",
    "speciality": "Diagnostics",
    "phone": "+1234567890",
    "address": "Princeton-Plainsboro",
}


async def test_list_providers_empty(auth_client):
    """List providers returns empty list for new household."""
    resp = await auth_client.get("/api/v1/providers")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_provider(auth_client):
    """Create a provider returns 201 with correct fields."""
    resp = await auth_client.post("/api/v1/providers", json=PROVIDER_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Dr. House"
    assert body["speciality"] == "Diagnostics"
    assert body["phone"] == "+1234567890"
    assert body["address"] == "Princeton-Plainsboro"
    assert "id" in body


async def test_get_provider(auth_client):
    """Get a provider by ID returns 200."""
    create_resp = await auth_client.post("/api/v1/providers", json=PROVIDER_PAYLOAD)
    assert create_resp.status_code == 201
    provider_id = create_resp.json()["id"]

    resp = await auth_client.get(f"/api/v1/providers/{provider_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == provider_id


async def test_update_provider(auth_client):
    """Update a provider returns 200 with updated fields."""
    create_resp = await auth_client.post("/api/v1/providers", json=PROVIDER_PAYLOAD)
    provider_id = create_resp.json()["id"]

    resp = await auth_client.put(
        f"/api/v1/providers/{provider_id}",
        json={"name": "Dr. Wilson"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Dr. Wilson"


async def test_list_providers_after_create(auth_client):
    """List providers returns at least one after creating."""
    await auth_client.post("/api/v1/providers", json=PROVIDER_PAYLOAD)
    resp = await auth_client.get("/api/v1/providers")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


async def test_delete_provider(auth_client):
    """Delete a provider returns 204, then list is empty."""
    create_resp = await auth_client.post("/api/v1/providers", json=PROVIDER_PAYLOAD)
    provider_id = create_resp.json()["id"]

    resp = await auth_client.delete(f"/api/v1/providers/{provider_id}")
    assert resp.status_code == 204

    list_resp = await auth_client.get("/api/v1/providers")
    assert list_resp.json() == []
