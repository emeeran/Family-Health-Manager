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


async def test_create_doctor_visit_exposes_report_field(auth_client):
    """A created doctor_visit response carries the transcription_report field."""
    member_id = await _create_member(auth_client)
    resp = await auth_client.post(f"/api/v1/members/{member_id}/records", json=RECORD_PAYLOAD)
    assert resp.status_code == 201
    assert "transcription_report" in resp.json()


async def test_create_record_runs_insight_post_commit(auth_client, monkeypatch):
    """Insight generation for a new record runs as a post-commit BackgroundTask.

    Regression for the race where it ran via loop.create_task at the next await
    (follow-up reminder / cache invalidation), BEFORE get_db() committed — so its
    own session couldn't see the just-inserted record and logged
    "Record ... not found for insight generation". A FastAPI BackgroundTask is
    awaited within the ASGI request cycle, so the spy must have been invoked with
    the created record's id by the time the POST returns.
    """
    from app.services.insight_service import InsightService

    invoked = {}

    async def _spy(self, record_id):
        invoked["record_id"] = str(record_id)
        return None

    monkeypatch.setattr(InsightService, "generate_record_insight", _spy)

    member_id = await _create_member(auth_client)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records", json=RECORD_PAYLOAD
    )
    assert resp.status_code == 201
    assert invoked.get("record_id") == resp.json()["id"]


async def test_regenerate_report_builds_transcription_report(auth_client):
    """The regenerate-report endpoint persists a transcription report.

    With no AI providers configured in the test env, the deterministic
    template fallback is used — the report must still be produced.
    """
    member_id = await _create_member(auth_client)
    create = await auth_client.post(f"/api/v1/members/{member_id}/records", json=RECORD_PAYLOAD)
    record_id = create.json()["id"]

    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records/{record_id}/regenerate-report"
    )
    assert resp.status_code == 200
    report = resp.json()["transcription_report"]
    assert report
    assert "Medical Records Transcription Report" in report


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

    resp = await auth_client.get(f"/api/v1/members/{member_id}/records/{record_id}")
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

    resp = await auth_client.delete(f"/api/v1/members/{member_id}/records/{record_id}")
    assert resp.status_code == 204
