"""End-to-end regression: the "Currently Taking Medicine" list must reflect
adds/edits made from the dedicated medication-management card.

ROOT CAUSE
----------
``get_active_medications`` is table-first: it returns from the ``medications``
table whenever the member has *any* row there, and only falls back to scanning
``health_records.clinical_data`` JSON when the table is empty. But the dedicated
medication CRUD endpoints (``POST/PUT/DELETE /members/{id}/medications``) write
to the record **JSON only** — they never touch the ``medications`` table. So for
any member with table-populated meds (anyone who created a doctor-visit record
via the records workflow), quick adds/edits are invisible.

These are HTTP-level e2e tests through the real endpoints and the real
``GET /members/{id}/dashboard`` read the UI uses. We seed the ``medications``
table directly (the production condition) rather than via the records router,
because ``create_record``'s ``if record.provider:`` lazy-load currently masks
``sync_from_record`` with a swallowed exception.
"""

import json
from datetime import date
from uuid import UUID

import pytest

from app.models.medication import Medication
from app.models.record import HealthRecord, RecordType

pytestmark = pytest.mark.asyncio

MEMBER = {
    "first_name": "Currently",
    "last_name": "Taking",
    "date_of_birth": "1990-01-01",
    "gender": "male",
    "relationship": "self",
}


async def _seed(db_session, member_id, medicine, dosage="1-1-1"):
    """Populate the medications table (fast path active) AND a backing health
    record so the CRUD endpoints can address it by record_id."""
    member_id = UUID(str(member_id))
    record = HealthRecord(
        family_member_id=member_id,
        record_type=RecordType.DOCTOR_VISIT,
        record_date=date.today(),
        clinical_data=json.dumps(
            {"_type": "structured", "prescriptions": [{"medicine": medicine, "dosage": dosage}]}
        ),
    )
    db_session.add(record)
    await db_session.flush()
    db_session.add(
        Medication(
            family_member_id=member_id,
            health_record_id=record.id,
            medicine=medicine,
            medicine_key=medicine.strip().lower(),
            dosage=dosage,
            status="active",
            start_date=date.today(),
            prescription_index=0,
        )
    )
    await db_session.flush()
    return record.id


async def _active_meds(client, member_id):
    resp = await client.get(f"/api/v1/members/{member_id}/dashboard")
    assert resp.status_code == 200, resp.text
    return resp.json().get("active_medications", [])


async def test_quick_add_visible_in_currently_taking(auth_client, db_session):
    """Adding a medicine from the card must show up even with table rows present."""
    member = (await auth_client.post("/api/v1/members", json=MEMBER)).json()["id"]
    await _seed(db_session, member, "Metformin")  # fast path active

    resp = await auth_client.post(
        f"/api/v1/members/{member}/medications",
        json={"medicine": "Atorvastatin 20mg", "dosage": "0-0-1", "type": "Tab"},
    )
    assert resp.status_code == 201, resp.text

    meds = await _active_meds(auth_client, member)
    assert any(m["medicine"] == "Atorvastatin 20mg" for m in meds), (
        f"quick-added medicine missing from Currently Taking: {meds}"
    )


async def test_quick_edit_reflected_in_currently_taking(auth_client, db_session):
    """Editing a dosage from the card must update the list even with the stale
    table row present."""
    member = (await auth_client.post("/api/v1/members", json=MEMBER)).json()["id"]
    await _seed(db_session, member, "Metformin", dosage="1-1-1")

    meds = await _active_meds(auth_client, member)
    met = next(m for m in meds if m["medicine"] == "Metformin")

    resp = await auth_client.put(
        f"/api/v1/members/{member}/medications",
        json={
            "record_id": met["record_id"],
            "prescription_index": met["prescription_index"],
            "data": {"medicine": "Metformin", "dosage": "2-2-2", "type": "Tab"},
        },
    )
    assert resp.status_code == 200, resp.text

    meds = await _active_meds(auth_client, member)
    met = next(m for m in meds if m["medicine"] == "Metformin")
    assert met["dosage"] == "2-2-2", f"edited dosage not reflected: {meds}"
