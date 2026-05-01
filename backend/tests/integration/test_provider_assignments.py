"""Integration tests for provider assignment endpoints."""
import pytest

pytestmark = pytest.mark.asyncio

MEMBER_PAYLOAD = {
    "first_name": "Prov",
    "last_name": "Test",
    "date_of_birth": "1985-03-20",
    "gender": "male",
    "relationship": "self",
}

PROVIDER_PAYLOAD = {
    "name": "Dr. Assigned",
    "speciality": "Cardiology",
}


async def _create_member(auth_client):
    resp = await auth_client.post("/api/v1/members", json=MEMBER_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_provider(auth_client):
    resp = await auth_client.post("/api/v1/providers", json=PROVIDER_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_list_member_providers_empty(auth_client):
    """New member has no assigned providers."""
    member_id = await _create_member(auth_client)
    resp = await auth_client.get(f"/api/v1/members/{member_id}/providers")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_assign_provider(auth_client):
    """Assign a provider to a member."""
    member_id = await _create_member(auth_client)
    provider_id = await _create_provider(auth_client)

    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/providers",
        json={"provider_id": provider_id},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["provider_id"] == provider_id
    assert body["family_member_id"] == member_id


async def test_remove_assignment(auth_client):
    """Remove a provider assignment."""
    member_id = await _create_member(auth_client)
    provider_id = await _create_provider(auth_client)

    assign_resp = await auth_client.post(
        f"/api/v1/members/{member_id}/providers",
        json={"provider_id": provider_id},
    )
    assignment_id = assign_resp.json()["id"]

    resp = await auth_client.delete(
        f"/api/v1/members/{member_id}/providers/{assignment_id}"
    )
    assert resp.status_code == 204

    # Verify it's gone
    list_resp = await auth_client.get(f"/api/v1/members/{member_id}/providers")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 0
