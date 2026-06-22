"""Regression: the "Currently Taking Medicine" list must reflect medicines
added/edited through the dedicated medication-management UI.

ROOT CAUSE (confirmed against production data)
----------------------------------------------
``MedicationService.get_active_medications`` is table-first:

    meds = SELECT FROM medications WHERE member AND status IN (active, completed)
    if meds:               # ← fast path
        return [from table]
    return scan_json(...)  # ← fallback only when the table is EMPTY

But the dedicated medication CRUD endpoints
(``POST/PUT/DELETE /members/{id}/medications``) write to
``health_records.clinical_data`` **JSON only** — they never insert/update the
``medications`` table (only ``sync_from_record``, called from the *records*
router, does). So once a member has *any* row in the ``medications`` table
(every member who created a doctor-visit record through the records workflow),
the fast path wins and:

  * a newly quick-added medicine (JSON-only) is **invisible**, and
  * a quick-edited dosage (JSON-only) is **stale**.

These tests reproduce that divergence at the service layer (fast, no AI) by
seeding the ``medications`` table directly — bypassing the records-router path,
whose ``if record.provider:`` lazy-load currently masks the bug by silently
skipping ``sync_from_record``.
"""

import json
from datetime import date
from uuid import uuid4

import pytest

from app.models.medication import Medication
from app.models.record import HealthRecord, RecordType
from app.services.medication_service import MedicationService


def _rx(medicine: str, dosage: str) -> str:
    return json.dumps(
        {"_type": "structured", "prescriptions": [{"medicine": medicine, "dosage": dosage}]}
    )


@pytest.mark.asyncio
async def test_quick_added_medicine_visible_when_table_has_rows(db_session):
    """REGRESSION: a medicine added via the JSON-only CRUD path must appear in
    the 'Currently Taking' list even when the ``medications`` table already has
    rows for the member (fast path active)."""
    member_id = uuid4()

    # Member already has a synced med: present in BOTH the table (cache) and a
    # backing JSON record (system of record). The table being non-empty is what
    # used to activate the stale fast-path.
    db_session.add(
        HealthRecord(
            family_member_id=member_id,
            record_type=RecordType.DOCTOR_VISIT,
            record_date=date.today(),
            clinical_data=_rx("Metformin", "1-1-1"),
        )
    )
    db_session.add(
        Medication(
            family_member_id=member_id,
            medicine="Metformin",
            medicine_key="metformin",
            dosage="1-1-1",
            status="active",
            start_date=date.today(),
        )
    )
    # The quick-add path creates a JSON record but does NOT write the table.
    db_session.add(
        HealthRecord(
            family_member_id=member_id,
            record_type=RecordType.DOCTOR_VISIT,
            record_date=date.today(),
            clinical_data=_rx("Atorvastatin 20mg", "0-0-1"),
        )
    )
    await db_session.flush()

    svc = MedicationService(db_session)
    meds = await svc.get_active_medications(member_id)
    names = [m["medicine"] for m in meds]

    assert "Metformin" in names
    assert "Atorvastatin 20mg" in names, (
        f"quick-added medicine missing from Currently Taking (read ignored JSON): {names}"
    )


@pytest.mark.asyncio
async def test_quick_edited_dosage_reflected_when_table_has_rows(db_session):
    """REGRESSION: editing a dosage via the JSON-only CRUD path must update the
    list even when the ``medications`` table (fast path) still holds the old row."""
    member_id = uuid4()
    record_id = uuid4()

    # Table row = what the read path returns (stale dosage).
    db_session.add(
        Medication(
            family_member_id=member_id,
            health_record_id=record_id,
            medicine="Metformin",
            medicine_key="metformin",
            dosage="1-1-1",
            status="active",
            start_date=date.today(),
            prescription_index=0,
        )
    )
    # Record JSON = what update_medication just wrote (new dosage).
    db_session.add(
        HealthRecord(
            id=record_id,
            family_member_id=member_id,
            record_type=RecordType.DOCTOR_VISIT,
            record_date=date.today(),
            clinical_data=_rx("Metformin", "2-2-2"),
        )
    )
    await db_session.flush()

    svc = MedicationService(db_session)
    meds = await svc.get_active_medications(member_id)
    met = next(m for m in meds if m["medicine"] == "Metformin")
    assert met["dosage"] == "2-2-2", (
        f"edited dosage not reflected (fast path served stale table row): {met}"
    )
