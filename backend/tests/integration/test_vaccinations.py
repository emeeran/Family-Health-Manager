"""Integration tests for vaccinations endpoints."""
import pytest

pytestmark = pytest.mark.asyncio

VACCINE_PAYLOAD = {
    "name": "COVID-19 Booster",
    "date_administered": "2026-01-15",
    "notes": "Pfizer bivalent",
}

MEMBER_PAYLOAD = {
    "first_name": "Vax",
    "last_name": "Test",
    "date_of_birth": "1990-06-15",
    "gender": "male",
    "relationship": "self",
}


async def _create_member(auth_client):
    resp = await auth_client.post("/api/v1/members", json=MEMBER_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_list_vaccinations_empty(auth_client):
    """List vaccinations returns empty for new member."""
    member_id = await _create_member(auth_client)
    resp = await auth_client.get(f"/api/v1/members/{member_id}/vaccinations")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_vaccination(auth_client):
    """Create a vaccination record."""
    member_id = await _create_member(auth_client)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/vaccinations", json=VACCINE_PAYLOAD
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "COVID-19 Booster"
    assert "id" in body


async def test_update_vaccination(auth_client):
    """Update a vaccination record."""
    member_id = await _create_member(auth_client)
    create_resp = await auth_client.post(
        f"/api/v1/members/{member_id}/vaccinations", json=VACCINE_PAYLOAD
    )
    vax_id = create_resp.json()["id"]

    resp = await auth_client.put(
        f"/api/v1/members/{member_id}/vaccinations/{vax_id}",
        json={"name": "COVID-19 Updated Booster", "date_administered": "2026-02-01"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "COVID-19 Updated Booster"


async def test_delete_vaccination(auth_client):
    """Delete a vaccination record."""
    member_id = await _create_member(auth_client)
    create_resp = await auth_client.post(
        f"/api/v1/members/{member_id}/vaccinations", json=VACCINE_PAYLOAD
    )
    vax_id = create_resp.json()["id"]

    resp = await auth_client.delete(
        f"/api/v1/members/{member_id}/vaccinations/{vax_id}"
    )
    assert resp.status_code == 204

    # Verify it's gone
    list_resp = await auth_client.get(f"/api/v1/members/{member_id}/vaccinations")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 0
