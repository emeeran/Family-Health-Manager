"""Integration tests for the /members/{id}/{drug-education,clinical-trials,condition-info} endpoints."""

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio

MEMBER_PAYLOAD = {
    "first_name": "Res",
    "last_name": "Tester",
    "date_of_birth": "1990-01-01",
    "gender": "female",
    "relationship": "self",
}


async def _create_member(auth_client) -> str:
    resp = await auth_client.post("/api/v1/members", json=MEMBER_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["id"]


# ── drug-education ────────────────────────────────────────────────────


async def test_drug_education_member_not_found(auth_client):
    from uuid import uuid4

    assert (
        await auth_client.get(f"/api/v1/members/{uuid4()}/drug-education", params={"medicine": "x"})
    ).status_code == 404


async def test_drug_education_requires_medicine(auth_client):
    mid = await _create_member(auth_client)
    assert (await auth_client.get(f"/api/v1/members/{mid}/drug-education")).status_code == 422


async def test_drug_education_returns_sections(auth_client):
    mid = await _create_member(auth_client)
    canned = {
        "medlineplus": [{"title": "Metformin", "url": "https://medlineplus.gov/x", "summary": ""}],
        "dailymed": [{"title": "Metformin Tab", "setid": "s", "url": "https://dailymed/..."}],
    }
    with patch("app.routers.member_resources.HealthResourcesService") as MockSvc:
        MockSvc.return_value.drug_education = AsyncMock(return_value=canned)
        resp = await auth_client.get(
            f"/api/v1/members/{mid}/drug-education", params={"medicine": "Metformin 500mg"}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["medlineplus"]) == 1 and len(body["dailymed"]) == 1


# ── clinical-trials ───────────────────────────────────────────────────


async def test_clinical_trials_member_not_found(auth_client):
    from uuid import uuid4

    assert (
        await auth_client.get(f"/api/v1/members/{uuid4()}/clinical-trials", params={"condition": "x"})
    ).status_code == 404


async def test_clinical_trials_requires_condition(auth_client):
    mid = await _create_member(auth_client)
    assert (await auth_client.get(f"/api/v1/members/{mid}/clinical-trials")).status_code == 422


async def test_clinical_trials_returns_trials(auth_client):
    mid = await _create_member(auth_client)
    canned = [{"nct_id": "NCT1", "title": "T", "status": "RECRUITING", "phase": "PHASE2", "conditions": ["Diabetes"], "url": "u"}]
    with patch("app.routers.member_resources.HealthResourcesService") as MockSvc:
        MockSvc.return_value.trials = AsyncMock(return_value=canned)
        resp = await auth_client.get(
            f"/api/v1/members/{mid}/clinical-trials", params={"condition": "diabetes", "limit": 5}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["trials"] == canned and body["condition"] == "diabetes"


async def test_clinical_trials_empty_when_none_found(auth_client):
    mid = await _create_member(auth_client)
    with patch("app.routers.member_resources.HealthResourcesService") as MockSvc:
        MockSvc.return_value.trials = AsyncMock(return_value=[])
        resp = await auth_client.get(
            f"/api/v1/members/{mid}/clinical-trials", params={"condition": "zzzunknown"}
        )
    assert resp.status_code == 200 and resp.json()["trials"] == []


# ── condition-info ────────────────────────────────────────────────────


async def test_condition_info_returns_results(auth_client):
    mid = await _create_member(auth_client)
    canned = [{"title": "Diabetes", "url": "https://medlineplus.gov/d", "summary": ""}]
    with patch("app.routers.member_resources.HealthResourcesService") as MockSvc:
        MockSvc.return_value.condition_info = AsyncMock(return_value=canned)
        resp = await auth_client.get(
            f"/api/v1/members/{mid}/condition-info",
            params={"code_system": "icd10", "code": "E11.9"},
        )
    assert resp.status_code == 200 and resp.json()["results"] == canned


async def test_condition_info_requires_code(auth_client):
    mid = await _create_member(auth_client)
    resp = await auth_client.get(
        f"/api/v1/members/{mid}/condition-info", params={"code_system": "icd10"}
    )
    assert resp.status_code == 422


# ── canadian-product (Health Canada DPD) ──────────────────────────────


async def test_canadian_product_member_not_found(auth_client):
    from uuid import uuid4

    assert (
        await auth_client.get(
            f"/api/v1/members/{uuid4()}/canadian-product", params={"din": "02246893"}
        )
    ).status_code == 404


async def test_canadian_product_rejects_bad_din(auth_client):
    mid = await _create_member(auth_client)
    assert (
        await auth_client.get(f"/api/v1/members/{mid}/canadian-product", params={"din": "123"})
    ).status_code == 422


async def test_canadian_product_returns_product(auth_client):
    mid = await _create_member(auth_client)
    canned = {
        "din": "02246893",
        "brand_name": "APO-VERAP SR",
        "descriptor": "",
        "company_name": "APOTEX INC",
        "class_name": "Human",
        "drug_code": 71120,
        "ai_group_no": "0113846001",
        "last_update_date": "2026-06-29",
    }
    with patch("app.routers.member_resources.HealthResourcesService") as MockSvc:
        MockSvc.return_value.canadian_product = AsyncMock(return_value=canned)
        resp = await auth_client.get(
            f"/api/v1/members/{mid}/canadian-product", params={"din": "02246893"}
        )
    assert resp.status_code == 200 and resp.json()["product"]["brand_name"] == "APO-VERAP SR"


async def test_canadian_product_not_found_returns_null(auth_client):
    mid = await _create_member(auth_client)
    with patch("app.routers.member_resources.HealthResourcesService") as MockSvc:
        MockSvc.return_value.canadian_product = AsyncMock(return_value=None)
        resp = await auth_client.get(
            f"/api/v1/members/{mid}/canadian-product", params={"din": "00000000"}
        )
    assert resp.status_code == 200 and resp.json()["product"] is None


# ── uk-alerts (MHRA / GOV.UK) ─────────────────────────────────────────


async def test_uk_alerts_member_not_found(auth_client):
    from uuid import uuid4

    assert (
        await auth_client.get(f"/api/v1/members/{uuid4()}/uk-alerts", params={"term": "x"})
    ).status_code == 404


async def test_uk_alerts_requires_term(auth_client):
    mid = await _create_member(auth_client)
    assert (await auth_client.get(f"/api/v1/members/{mid}/uk-alerts")).status_code == 422


async def test_uk_alerts_returns_alerts(auth_client):
    mid = await _create_member(auth_client)
    canned = [
        {
            "title": "Metformin MHRA Update",
            "url": "https://www.gov.uk/government/news/x",
            "description": "",
            "date": "2019-12-06",
            "format": "press_release",
        }
    ]
    with patch("app.routers.member_resources.HealthResourcesService") as MockSvc:
        MockSvc.return_value.uk_alerts = AsyncMock(return_value=canned)
        resp = await auth_client.get(
            f"/api/v1/members/{mid}/uk-alerts", params={"term": "metformin", "limit": 5}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["alerts"] == canned and body["term"] == "metformin"


async def test_uk_alerts_empty_when_none(auth_client):
    mid = await _create_member(auth_client)
    with patch("app.routers.member_resources.HealthResourcesService") as MockSvc:
        MockSvc.return_value.uk_alerts = AsyncMock(return_value=[])
        resp = await auth_client.get(
            f"/api/v1/members/{mid}/uk-alerts", params={"term": "zzzunknown"}
        )
    assert resp.status_code == 200 and resp.json()["alerts"] == []
