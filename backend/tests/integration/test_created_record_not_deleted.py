"""Medication dedup behavior: "latest Rx wins, then offer to modify".

Creating a record must NOT silently prune or delete other records' prescriptions
— the dedup runs only when the user confirms the medication-sync dialog. And
when it does run, it modifies prescriptions (keeps the newest) without ever
soft-deleting a visit record.
"""

import json

import pytest

pytestmark = pytest.mark.asyncio

MEMBER = {
    "first_name": "Regression",
    "last_name": "Patient",
    "date_of_birth": "1990-01-01",
    "gender": "male",
    "relationship": "self",
}


def _visit_with_rx(medicine: str, record_date: str) -> dict:
    clinical = json.dumps(
        {
            "_type": "structured",
            "_version": 1,
            "_recordType": "doctor_visit",
            "prescriptions": [{"medicine": medicine, "dosage": "1-1-1", "type": "Tab"}],
        }
    )
    return {
        "record_type": "doctor_visit",
        "record_date": record_date,
        "clinical_data": clinical,
        "diagnosis": "Visit",
    }


async def _create_member(client) -> str:
    resp = await client.post("/api/v1/members", json=MEMBER)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _prescriptions(resp_json: dict) -> list[dict]:
    parsed = json.loads(resp_json["clinical_data"])
    return parsed.get("prescriptions", []) if isinstance(parsed, dict) else []


async def test_create_does_not_silently_dedup_other_records(auth_client):
    """Creating a record with a duplicate medicine must not touch other records
    — no silent pruning/deletion on create. The med-sync dialog offers that."""
    member_id = await _create_member(auth_client)

    newer = await auth_client.post(
        f"/api/v1/members/{member_id}/records", json=_visit_with_rx("Metformin", "2026-06-21")
    )
    older = await auth_client.post(
        f"/api/v1/members/{member_id}/records", json=_visit_with_rx("Metformin", "2024-01-15")
    )
    assert older.status_code == 201, older.text

    # Both records survive, and both still carry their prescription (no silent
    # dedup happened on create).
    for rid in (newer.json()["id"], older.json()["id"]):
        got = await auth_client.get(f"/api/v1/members/{member_id}/records/{rid}")
        assert got.status_code == 200, got.text
        assert got.json()["is_deleted"] is False
        assert any(rx["medicine"] == "Metformin" for rx in _prescriptions(got.json()))


async def test_med_sync_modifies_prescriptions_without_deleting_records(auth_client):
    """When the med-sync dialog is applied (latest Rx wins), the older duplicate
    prescription is pruned from clinical_data but the visit record is preserved
    (not soft-deleted)."""
    member_id = await _create_member(auth_client)

    newer = (
        await auth_client.post(
            f"/api/v1/members/{member_id}/records", json=_visit_with_rx("Metformin", "2026-06-21")
        )
    ).json()
    older = (
        await auth_client.post(
            f"/api/v1/members/{member_id}/records", json=_visit_with_rx("Metformin", "2026-01-15")
        )
    ).json()

    # Apply the med-sync offer for Metformin (the dialog's confirm action).
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/medications/apply-sync",
        json={"apply_added": [], "apply_updated": [], "apply_removed": ["Metformin"]},
    )
    assert resp.status_code == 200, resp.text

    older_after = await auth_client.get(f"/api/v1/members/{member_id}/records/{older['id']}")
    newer_after = await auth_client.get(f"/api/v1/members/{member_id}/records/{newer['id']}")
    assert older_after.status_code == 200 and newer_after.status_code == 200

    # Latest Rx wins: the NEWER record keeps Metformin; the OLDER record's
    # duplicate is pruned — but the older record itself is NOT deleted.
    assert any(rx["medicine"] == "Metformin" for rx in _prescriptions(newer_after.json()))
    assert not any(rx["medicine"] == "Metformin" for rx in _prescriptions(older_after.json()))
    assert older_after.json()["is_deleted"] is False
