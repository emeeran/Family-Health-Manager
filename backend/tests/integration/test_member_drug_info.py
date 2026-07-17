"""Integration tests for the /members/{id}/drug-* endpoints (openFDA-backed).

External lookups are mocked at the service boundary so no real network is hit.
Mirrors the member/record setup helpers in test_drug_interactions.py.
"""

import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio

MEMBER_PAYLOAD = {
    "first_name": "Drug",
    "last_name": "Info",
    "date_of_birth": "1960-01-01",
    "gender": "male",
    "relationship": "self",
}


async def _create_member(auth_client) -> str:
    resp = await auth_client.post("/api/v1/members", json=MEMBER_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _add_meds(auth_client, member_id, medicines):
    """Attach active prescriptions via a doctor_visit record."""
    record_date = date.today().isoformat()
    prescriptions = [
        {"medicine": m, "type": "Tab", "dosage": "1-0-1", "duration": "90 days"} for m in medicines
    ]
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records",
        json={
            "record_type": "doctor_visit",
            "record_date": record_date,
            "clinical_data": json.dumps({"_type": "structured", "prescriptions": prescriptions}),
            "diagnosis": "Routine",
        },
    )
    assert resp.status_code == 201


# ── drug-recalls ──────────────────────────────────────────────────────


async def test_recalls_member_not_found(auth_client):
    from uuid import uuid4

    resp = await auth_client.get(f"/api/v1/members/{uuid4()}/drug-recalls")
    assert resp.status_code == 404


async def test_recalls_empty_for_member_with_no_meds(auth_client):
    member_id = await _create_member(auth_client)
    with patch("app.routers.member_drug_info.DrugInfoService") as MockSvc:
        MockSvc.return_value.recalls = AsyncMock(return_value=[])
        resp = await auth_client.get(f"/api/v1/members/{member_id}/drug-recalls")
    assert resp.status_code == 200
    body = resp.json()
    assert body["recalls"] == []
    assert body["medications_checked"] == 0
    assert "checked_at" in body


async def test_recalls_returns_matched_reports(auth_client):
    member_id = await _create_member(auth_client)
    await _add_meds(auth_client, member_id, ["Metformin 500mg", "Atorvastatin 20mg"])
    canned = [
        {
            "generic_name": "metformin",
            "product_description": "Metformin 500mg",
            "reason_for_recall": "NDMA impurity",
            "classification": "Class II",
            "status": "Ongoing",
            "recalling_firm": "Acme",
            "recall_initiation_date": "20240101",
            "code_info": "",
            "matched_medications": ["metformin"],
        }
    ]
    with patch("app.routers.member_drug_info.DrugInfoService") as MockSvc:
        MockSvc.return_value.recalls = AsyncMock(return_value=canned)
        resp = await auth_client.get(f"/api/v1/members/{member_id}/drug-recalls")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["recalls"]) == 1
    assert body["recalls"][0]["reason_for_recall"] == "NDMA impurity"
    assert body["medications_checked"] == 2


# ── drug-label ────────────────────────────────────────────────────────


async def test_label_requires_medicine_param(auth_client):
    member_id = await _create_member(auth_client)
    resp = await auth_client.get(f"/api/v1/members/{member_id}/drug-label")
    assert resp.status_code == 422  # missing required query param


async def test_label_returns_sections(auth_client):
    member_id = await _create_member(auth_client)
    canned = {
        "generic_name": "metformin",
        "brand_name": "Glucophage",
        "sections": {"indications_and_usage": "Type 2 diabetes"},
    }
    with patch("app.routers.member_drug_info.DrugInfoService") as MockSvc:
        MockSvc.return_value.label = AsyncMock(return_value=canned)
        resp = await auth_client.get(
            f"/api/v1/members/{member_id}/drug-label", params={"medicine": "Metformin 500mg"}
        )
    assert resp.status_code == 200
    assert resp.json()["label"]["generic_name"] == "metformin"


async def test_label_not_found_returns_null(auth_client):
    member_id = await _create_member(auth_client)
    with patch("app.routers.member_drug_info.DrugInfoService") as MockSvc:
        MockSvc.return_value.label = AsyncMock(return_value=None)
        resp = await auth_client.get(
            f"/api/v1/members/{member_id}/drug-label", params={"medicine": "unknowndrug"}
        )
    assert resp.status_code == 200
    assert resp.json()["label"] is None


# ── drug-adverse-events ───────────────────────────────────────────────


async def test_adverse_events_returns_reactions(auth_client):
    member_id = await _create_member(auth_client)
    canned = [{"term": "Nausea", "count": 42}, {"term": "Headache", "count": 7}]
    with patch("app.routers.member_drug_info.DrugInfoService") as MockSvc:
        MockSvc.return_value.adverse_events = AsyncMock(return_value=canned)
        resp = await auth_client.get(
            f"/api/v1/members/{member_id}/drug-adverse-events", params={"medicine": "Metformin 500mg"}
        )
    assert resp.status_code == 200
    assert resp.json()["events"] == canned


async def test_adverse_events_requires_medicine_param(auth_client):
    member_id = await _create_member(auth_client)
    resp = await auth_client.get(f"/api/v1/members/{member_id}/drug-adverse-events")
    assert resp.status_code == 422
