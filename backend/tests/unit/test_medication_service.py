"""Unit tests for medication service — duration parsing & active medications."""
import json
from datetime import date, timedelta
from uuid import uuid4

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.medication_service import MedicationService
from app.core.parsing import parse_duration


def _empty_scalars():
    """Return a mock result whose .scalars().all() returns []."""
    return MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))


# ── _parse_duration ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "input_str, expected_days",
    [
        ("30 days", 30),
        ("30 day", 30),
        ("7 days", 7),
        ("2 weeks", 14),
        ("1 week", 7),
        ("3 months", 90),
        ("1 month", 30),
        ("6 months", 180),
        ("14", 14),
        ("60", 60),
        ("", 30),       # empty → default 30
        (None, 30),     # None → default 30
        ("ongoing", 30),  # unrecognized → default 30
        ("lifelong", 30),
        ("  90 days  ", 90),  # whitespace trimmed
    ],
)
def test_parse_duration(input_str, expected_days):
    assert parse_duration(input_str) == expected_days


# ── MedicationService.get_active_medications ─────────────────────────


def _make_record(
    record_id=None,
    record_date=None,
    clinical_data=None,
    record_type="doctor_visit",
):
    """Build a mock HealthRecord."""
    r = MagicMock()
    r.id = record_id or uuid4()
    r.record_date = record_date or date.today()
    r.clinical_data = clinical_data
    r.record_type = MagicMock(value=record_type)
    return r


def _clinical_data(prescriptions, provider_name="Dr. Test", medication_sync=True):
    """Build a structured clinical_data JSON string."""
    data = {
        "_type": "structured",
        "prescriptions": prescriptions,
    }
    if provider_name:
        data["_provider_name"] = provider_name
    if not medication_sync:
        data["_medication_sync"] = False
    return json.dumps(data)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def med_service(mock_db):
    return MedicationService(mock_db)


@pytest.mark.asyncio
async def test_get_active_medications_empty(med_service, mock_db):
    """No records → empty list."""
    mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
    result = await med_service.get_active_medications(uuid4())
    assert result == []


@pytest.mark.asyncio
async def test_get_active_medications_single_record(med_service, mock_db):
    """Single record with 3 prescriptions returns 3 medications."""
    today = date.today()
    rx = [
        {"medicine": "Metformin 500mg", "type": "Tab", "dosage": "1-0-1", "duration": "30 days"},
        {"medicine": "Glimepiride 2mg", "type": "Tab", "dosage": "0-0-1", "duration": "30 days"},
        {"medicine": "Atorvastatin 10mg", "type": "Tab", "dosage": "0-1-0", "duration": "90 days"},
    ]
    record = _make_record(
        record_date=today,
        clinical_data=_clinical_data(rx),
    )

    # First call: Medication table (empty) → triggers JSON fallback
    # Second call: HealthRecord table (has data)
    scalars_empty = _empty_scalars()
    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = [record]
    mock_db.execute = AsyncMock(side_effect=[scalars_empty, scalars_result])

    result = await med_service.get_active_medications(uuid4())

    assert len(result) == 3
    assert result[0]["medicine"] == "Metformin 500mg"
    assert result[0]["status"] == "active"
    assert result[1]["medicine"] == "Glimepiride 2mg"
    assert result[2]["medicine"] == "Atorvastatin 10mg"


@pytest.mark.asyncio
async def test_get_active_medications_deduplication(med_service, mock_db):
    """Duplicate medicine across records: keeps the latest only."""
    member_id = uuid4()
    old_date = date.today() - timedelta(days=60)
    new_date = date.today() - timedelta(days=5)

    old_rx = [{"medicine": "Metformin 500mg", "type": "Tab", "dosage": "1-0-1", "duration": "30 days"}]
    new_rx = [{"medicine": "Metformin 500mg", "type": "Tab", "dosage": "1-0-1", "duration": "60 days"}]

    old_record = _make_record(record_date=old_date, clinical_data=_clinical_data(old_rx))
    new_record = _make_record(record_date=new_date, clinical_data=_clinical_data(new_rx))

    scalars_empty = _empty_scalars()
    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = [new_record, old_record]
    mock_db.execute = AsyncMock(side_effect=[scalars_empty, scalars_result])

    result = await med_service.get_active_medications(member_id)

    # Only one Metformin entry (the latest, dedup by full name match)
    assert len(result) == 1
    assert result[0]["medicine"] == "Metformin 500mg"


@pytest.mark.asyncio
async def test_get_active_medications_completed_status(med_service, mock_db):
    """Medication with end_date in the past has status 'completed'."""
    old_date = date.today() - timedelta(days=60)
    rx = [{"medicine": "Amoxicillin 500mg", "type": "Cap", "dosage": "1-0-1", "duration": "7 days"}]
    record = _make_record(
        record_date=old_date,
        clinical_data=_clinical_data(rx),
    )

    scalars_empty = _empty_scalars()
    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = [record]
    mock_db.execute = AsyncMock(side_effect=[scalars_empty, scalars_result])

    result = await med_service.get_active_medications(uuid4())

    assert len(result) == 1
    assert result[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_get_active_medications_skips_sync_false(med_service, mock_db):
    """Records with _medication_sync=false are skipped."""
    today = date.today()
    rx = [{"medicine": "Metformin 500mg", "type": "Tab", "dosage": "1-0-1", "duration": "30 days"}]
    record = _make_record(
        record_date=today,
        clinical_data=_clinical_data(rx, medication_sync=False),
    )

    scalars_empty = _empty_scalars()
    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = [record]
    mock_db.execute = AsyncMock(side_effect=[scalars_empty, scalars_result])

    result = await med_service.get_active_medications(uuid4())
    assert result == []


@pytest.mark.asyncio
async def test_get_active_medications_skips_null_clinical_data(med_service, mock_db):
    """Records with null clinical_data are skipped."""
    record = _make_record(
        record_date=date.today(),
        clinical_data=None,
    )

    scalars_empty = _empty_scalars()
    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = [record]
    mock_db.execute = AsyncMock(side_effect=[scalars_empty, scalars_result])

    result = await med_service.get_active_medications(uuid4())
    assert result == []


@pytest.mark.asyncio
async def test_get_active_medications_skips_non_structured(med_service, mock_db):
    """Records with _type != 'structured' are skipped."""
    record = _make_record(
        record_date=date.today(),
        clinical_data=json.dumps({"prescriptions": [{"medicine": "Test"}]}),
    )

    scalars_empty = _empty_scalars()
    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = [record]
    mock_db.execute = AsyncMock(side_effect=[scalars_empty, scalars_result])

    result = await med_service.get_active_medications(uuid4())
    assert result == []


@pytest.mark.asyncio
async def test_get_active_medications_skips_empty_medicine_name(med_service, mock_db):
    """Prescriptions with empty medicine name are skipped."""
    rx = [
        {"medicine": "", "type": "Tab", "dosage": "1-0-1", "duration": "30 days"},
        {"medicine": "Metformin 500mg", "type": "Tab", "dosage": "1-0-1", "duration": "30 days"},
    ]
    record = _make_record(
        record_date=date.today(),
        clinical_data=_clinical_data(rx),
    )

    scalars_empty = _empty_scalars()
    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = [record]
    mock_db.execute = AsyncMock(side_effect=[scalars_empty, scalars_result])

    result = await med_service.get_active_medications(uuid4())
    assert len(result) == 1
    assert result[0]["medicine"] == "Metformin 500mg"
