"""Integration tests for health records CRUD."""
import pytest


pytestmark = pytest.mark.asyncio

MEMBER_PAYLOAD = {
    "first_name": "Record",
    "last_name": "Patient",
    "date_of_birth": "1985-03-20",
    "gender": "male",
    "relationship": "self",
}

RECORD_PAYLOAD = {
    "record_type": "doctor_visit",
    "record_date": "2025-01-15",
    "clinical_data": "Routine checkup, all vitals normal",
    "diagnosis": "Healthy",
}


async def _create_member(auth_client) -> str:
    """Helper: create a family member and return its ID."""
    resp = await auth_client.post("/api/v1/members", json=MEMBER_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_create_record(auth_client):
    """Create a health record returns 201."""
    member_id = await _create_member(auth_client)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records",
        json=RECORD_PAYLOAD,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["clinical_data"] == "Routine checkup, all vitals normal"
    assert body["record_type"] == "doctor_visit"
    assert body["is_deleted"] is False


async def test_list_records(auth_client):
    """List records returns created records."""
    member_id = await _create_member(auth_client)
    await auth_client.post(
        f"/api/v1/members/{member_id}/records",
        json=RECORD_PAYLOAD,
    )
    resp = await auth_client.get(f"/api/v1/members/{member_id}/records")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1


async def test_get_record(auth_client):
    """Get a specific record returns 200."""
    member_id = await _create_member(auth_client)
    create_resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records",
        json=RECORD_PAYLOAD,
    )
    record_id = create_resp.json()["id"]

    resp = await auth_client.get(
        f"/api/v1/members/{member_id}/records/{record_id}"
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == record_id


async def test_delete_record(auth_client):
    """Soft-delete a record returns 204."""
    member_id = await _create_member(auth_client)
    create_resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records",
        json=RECORD_PAYLOAD,
    )
    record_id = create_resp.json()["id"]

    resp = await auth_client.delete(
        f"/api/v1/members/{member_id}/records/{record_id}"
    )
    assert resp.status_code == 204
