"""Integration tests for health records CRUD."""

import json

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


async def test_create_record_syncs_medications_and_lab_results_inline(auth_client, db_session):
    """Both medication and lab-result syncs run during save.

    Regression for the shared-AsyncSession hazard: the syncs used to run
    concurrently on one session via asyncio.gather, which could trip a
    concurrent-use error that each sync's try/except silently swallowed —
    dropping one or both syncs.
    """
    from sqlalchemy import select
    from uuid import UUID

    from app.models.lab_result import LabResult
    from app.models.medication import Medication

    member_id = await _create_member(auth_client)
    member_uuid = UUID(member_id)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records",
        json={
            "record_type": "doctor_visit",
            "record_date": "2025-01-15",
            "clinical_data": json.dumps(
                {
                    "_type": "structured",
                    "prescriptions": [
                        {"medicine": "Metformin", "dosage": "500mg", "duration": "30 days"}
                    ],
                    "lab_results": [{"test_name": "HbA1c", "result": "6.4"}],
                }
            ),
        },
    )
    assert resp.status_code == 201

    meds = (
        (
            await db_session.execute(
                select(Medication).where(Medication.family_member_id == member_uuid)
            )
        )
        .scalars()
        .all()
    )
    labs = (
        (
            await db_session.execute(
                select(LabResult).where(LabResult.family_member_id == member_uuid)
            )
        )
        .scalars()
        .all()
    )
    assert meds, "medication sync was dropped during save"
    assert labs, "lab result sync was dropped during save"


async def test_create_doctor_visit_exposes_report_field(auth_client):
    """A created doctor_visit response carries the transcription_report field."""
    member_id = await _create_member(auth_client)
    resp = await auth_client.post(f"/api/v1/members/{member_id}/records", json=RECORD_PAYLOAD)
    assert resp.status_code == 201
    assert "transcription_report" in resp.json()


async def test_create_record_invokes_insight_background_task(auth_client, monkeypatch):
    """Insight generation is dispatched as a FastAPI BackgroundTask on create
    (registered in the request, run during response send). The spy must have been
    invoked with the created record's id by the time the POST returns. Visibility
    of the record to the task's own session is covered by
    test_create_record_commits_before_background_tasks."""
    from app.services.insight_service import InsightService

    invoked = {}

    async def _spy(self, record_id):
        invoked["record_id"] = str(record_id)
        return None

    monkeypatch.setattr(InsightService, "generate_record_insight", _spy)

    member_id = await _create_member(auth_client)
    resp = await auth_client.post(f"/api/v1/members/{member_id}/records", json=RECORD_PAYLOAD)
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


async def test_create_record_commits_before_background_tasks(
    auth_client, db_session, monkeypatch, caplog
):
    """create_record commits before background tasks run, so the insight task's
    OWN session can see the record.

    FastAPI runs BackgroundTasks while get_db() is still open (request-scoped:
    it commits/closes only AFTER background tasks). Without create_record's
    explicit commit, the insight task queries an uncommitted row and logs
    'Record ... not found for insight generation'. insight_service imports
    SessionLocal at module level, so we patch THAT reference to the test engine
    (otherwise it queries the production DB and "not found" is meaningless).
    """
    import app.services.insight_service as isvc
    from sqlalchemy.ext.asyncio import AsyncSession

    monkeypatch.setattr(
        isvc, "SessionLocal", lambda: AsyncSession(db_session.bind, expire_on_commit=False)
    )

    # Stub the AI call so the test doesn't depend on Ollama; the point is that
    # the record is FOUND, not that an insight is produced.
    async def _no_ai(self, **_kw):
        return None

    monkeypatch.setattr(isvc.AIService, "generate_insight", _no_ai)

    member_id = await _create_member(auth_client)
    with caplog.at_level("WARNING"):
        resp = await auth_client.post(
            f"/api/v1/members/{member_id}/records",
            json={
                "record_type": "misc_record",
                "record_date": "2026-06-22",
                "clinical_data": "probe",
            },
        )
    assert resp.status_code == 201
    assert "not found for insight generation" not in caplog.text


async def test_update_record_commits_before_background_task(auth_client, db_session, monkeypatch):
    """update_record commits before the transcription-report background task
    fires, so the task's own session reads the UPDATED clinical_data.

    Mirrors test_create_record_commits_before_background_tasks for the update
    path (the streamline branch fixed create_record but not update_record).
    Without the explicit commit, the task's own session reads the pre-update row
    (or hits 'database is locked' on SQLite) and the report is built from stale
    data.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.record import HealthRecord
    import app.routers.health_records as hr

    seen: dict = {}

    async def _spy(record_id, household_id, member_id):
        # The real task opens its OWN session; do the same on the test engine to
        # check what clinical_data it reads at task-run time.
        async with AsyncSession(db_session.bind, expire_on_commit=False) as fresh:
            row = (
                await fresh.execute(select(HealthRecord).where(HealthRecord.id == record_id))
            ).scalar_one_or_none()
        seen["clinical_data"] = row.clinical_data if row else None

    monkeypatch.setattr(hr, "_generate_transcription_report_background", _spy)

    member_id = await _create_member(auth_client)
    create = await auth_client.post(
        f"/api/v1/members/{member_id}/records",
        json={
            "record_type": "doctor_visit",
            "record_date": "2026-06-22",
            "clinical_data": "ORIGINAL NOTES",
        },
    )
    assert create.status_code == 201
    record_id = create.json()["id"]

    # Update clinical_data — this triggers the transcription-report background task.
    resp = await auth_client.put(
        f"/api/v1/members/{member_id}/records/{record_id}",
        json={"clinical_data": "UPDATED NOTES"},
    )
    assert resp.status_code == 200
    # The background task has run by the time PUT returns; it must have seen the
    # committed UPDATE, not the stale original.
    assert seen.get("clinical_data") == "UPDATED NOTES"
