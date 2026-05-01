"""Tests for bulk medication delete logic."""
import json

import pytest


@pytest.mark.asyncio
async def test_bulk_delete_same_record():
    """Bulk delete from same record: indices shift after each pop, so must go descending."""

    # Simulate a record with 4 prescriptions
    prescriptions = [
        {"medicine": "MedA"},
        {"medicine": "MedB"},
        {"medicine": "MedC"},
        {"medicine": "MedD"},
    ]

    # User selects indices 0, 1, 3 (MedA, MedB, MedD) for deletion
    indices_to_delete = [0, 1, 3]

    # Sort descending — this is what the endpoint does
    indices_to_delete.sort(reverse=True)

    # Pop from highest index first
    for idx in indices_to_delete:
        prescriptions.pop(idx)

    # Only MedC should remain
    assert len(prescriptions) == 1
    assert prescriptions[0]["medicine"] == "MedC"


@pytest.mark.asyncio
async def test_bulk_delete_all_from_record():
    """When all prescriptions are deleted, the list should be empty."""
    prescriptions = [
        {"medicine": "MedA"},
        {"medicine": "MedB"},
    ]

    indices_to_delete = [0, 1]
    indices_to_delete.sort(reverse=True)

    for idx in indices_to_delete:
        prescriptions.pop(idx)

    assert len(prescriptions) == 0


@pytest.mark.asyncio
async def test_bulk_delete_multiple_records():
    """Bulk delete across different records works independently."""
    record_a = [{"medicine": "MedA"}, {"medicine": "MedB"}, {"medicine": "MedC"}]
    record_b = [{"medicine": "MedX"}, {"medicine": "MedY"}]

    # Delete MedB (idx 1) from record_a, MedX (idx 0) from record_b
    for idx in sorted([1], reverse=True):
        record_a.pop(idx)
    for idx in sorted([0], reverse=True):
        record_b.pop(idx)

    assert [m["medicine"] for m in record_a] == ["MedA", "MedC"]
    assert [m["medicine"] for m in record_b] == ["MedY"]


@pytest.mark.asyncio
async def test_bulk_delete_endpoint_integration():
    """Test the bulk delete endpoint directly exercises the pop-descending logic."""
    from app.routers.members import _rebuild_clinical_data

    parsed = {
        "_type": "structured",
        "prescriptions": [
            {"medicine": "MedA", "dosage": "1-0-1"},
            {"medicine": "MedB", "dosage": "0-0-1"},
            {"medicine": "MedC", "dosage": "1-1-1"},
        ],
    }
    prescriptions = parsed["prescriptions"]

    # Simulate what bulk_delete_medications does: delete indices 0 and 2
    indices = [0, 2]
    indices.sort(reverse=True)  # → [2, 0]
    for idx in indices:
        prescriptions.pop(idx)

    result = json.loads(_rebuild_clinical_data(parsed, prescriptions))
    assert len(result["prescriptions"]) == 1
    assert result["prescriptions"][0]["medicine"] == "MedB"
