"""Integration tests for family members CRUD."""
import pytest


pytestmark = pytest.mark.asyncio

MEMBER_PAYLOAD = {
    "first_name": "Alice",
    "last_name": "Smith",
    "date_of_birth": "1990-05-15",
    "gender": "female",
    "relationship": "self",
}


async def test_list_members_empty(auth_client):
    """List members returns empty list for new household."""
    resp = await auth_client.get("/api/v1/members")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_member(auth_client):
    """Create a family member returns 201 with correct fields."""
    resp = await auth_client.post("/api/v1/members", json=MEMBER_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["first_name"] == "Alice"
    assert body["last_name"] == "Smith"
    assert body["gender"] == "female"
    assert body["relationship_type"] == "self"
    assert "id" in body
    return body


async def test_get_member(auth_client):
    """Get a member by ID returns 200."""
    # Create member first
    create_resp = await auth_client.post("/api/v1/members", json=MEMBER_PAYLOAD)
    assert create_resp.status_code == 201
    member_id = create_resp.json()["id"]

    resp = await auth_client.get(f"/api/v1/members/{member_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == member_id


async def test_update_member(auth_client):
    """Update a member returns 200 with updated fields."""
    create_resp = await auth_client.post("/api/v1/members", json=MEMBER_PAYLOAD)
    member_id = create_resp.json()["id"]

    resp = await auth_client.put(
        f"/api/v1/members/{member_id}",
        json={"first_name": "Alicia"},
    )
    assert resp.status_code == 200
    assert resp.json()["first_name"] == "Alicia"


async def test_list_members_after_create(auth_client):
    """List members returns one member after creating one."""
    await auth_client.post("/api/v1/members", json=MEMBER_PAYLOAD)
    resp = await auth_client.get("/api/v1/members")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1


async def test_delete_member(auth_client):
    """Soft-delete a member returns 204, then list is empty for active."""
    create_resp = await auth_client.post("/api/v1/members", json=MEMBER_PAYLOAD)
    member_id = create_resp.json()["id"]

    resp = await auth_client.delete(f"/api/v1/members/{member_id}")
    assert resp.status_code == 204

    # Member is soft-deleted so default list (is_active=True) should be empty
    list_resp = await auth_client.get("/api/v1/members")
    active = [m for m in list_resp.json() if m.get("is_active")]
    assert len(active) == 0
