"""Regression: a just-created doctor_visit must not be soft-deleted by the
outdated-prescription cleanup that runs during create.

remove_outdated_prescriptions keeps only the newest prescription per medicine
and soft-deletes records whose prescriptions are all stripped as older
duplicates. When a new record has a past date and a medicine that already
exists in a newer record, the new record was being soft-deleted mid-create — so
the handler still returned it (201) but the post-save GET /records/{id} 404'd.
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


async def test_created_record_survives_duplicate_medication_in_newer_record(auth_client):
    member_id = await _create_member(auth_client)

    # Existing NEWER record with medicine X.
    newer = await auth_client.post(
        f"/api/v1/members/{member_id}/records", json=_visit_with_rx("Metformin", "2026-06-21")
    )
    assert newer.status_code == 201, newer.text

    # Create an OLDER record with the same medicine — this is the regression:
    # remove_outdated_prescriptions used to soft-delete it mid-create.
    created = await auth_client.post(
        f"/api/v1/members/{member_id}/records", json=_visit_with_rx("Metformin", "2024-01-15")
    )
    assert created.status_code == 201, created.text
    created_id = created.json()["id"]

    # The just-created record must still be retrievable (not soft-deleted).
    fetched = await auth_client.get(f"/api/v1/members/{member_id}/records/{created_id}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["is_deleted"] is False
