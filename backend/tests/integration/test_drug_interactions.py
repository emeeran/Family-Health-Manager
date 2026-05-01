"""Integration tests for drug interaction API endpoints."""
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

import pytest

pytestmark = pytest.mark.asyncio

MEMBER_PAYLOAD = {
    "first_name": "Drug",
    "last_name": "Tester",
    "date_of_birth": "1960-01-01",
    "gender": "male",
    "relationship": "self",
}


async def _create_member(auth_client) -> str:
    resp = await auth_client.post("/api/v1/members", json=MEMBER_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_doctor_visit_with_rx(auth_client, member_id, medicines, days_ago=0):
    """Create a doctor_visit record with structured prescriptions."""
    from datetime import date

    record_date = (date.today() - timedelta(days=days_ago)).isoformat()
    prescriptions = [
        {"medicine": m, "type": "Tab", "dosage": "1-0-1", "duration": "90 days"}
        for m in medicines
    ]
    clinical_data = json.dumps({
        "_type": "structured",
        "prescriptions": prescriptions,
    })

    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records",
        json={
            "record_type": "doctor_visit",
            "record_date": record_date,
            "clinical_data": clinical_data,
            "diagnosis": "Routine follow-up",
        },
    )
    assert resp.status_code == 201
    return resp.json()


MOCK_INTERACTIONS = [
    {
        "drugs": ["Warfarin", "Aspirin"],
        "severity": "high",
        "description": "Increased risk of bleeding",
        "recommendation": "Monitor INR closely",
    },
    {
        "drugs": ["Warfarin", "Omeprazole"],
        "severity": "moderate",
        "description": "Omeprazole may increase warfarin levels",
        "recommendation": "Check INR more frequently",
    },
]


async def _mock_check_interactions(medications):
    """Deterministic mock — returns interactions based on medication count."""
    if len(medications) < 2:
        return []
    return MOCK_INTERACTIONS


# ── GET /{member_id}/latest-drug-interactions ────────────────────────


async def test_latest_interactions_member_not_found(auth_client):
    """404 for non-existent member."""
    from uuid import uuid4
    fake_id = str(uuid4())
    resp = await auth_client.get(f"/api/v1/members/{fake_id}/latest-drug-interactions")
    assert resp.status_code == 404


async def test_latest_interactions_under_2_medications(auth_client):
    """Returns empty when member has < 2 active medications."""
    member_id = await _create_member(auth_client)
    # Only 1 medication
    await _create_doctor_visit_with_rx(auth_client, member_id, ["Metformin 500mg"])

    with patch("app.services.ai_service.AIService.check_drug_interactions", new_callable=AsyncMock) as mock_ai:
        resp = await auth_client.get(f"/api/v1/members/{member_id}/latest-drug-interactions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["interactions"] == []
        assert body["medications_checked"] == 1
        mock_ai.assert_not_called()


async def test_latest_interactions_generates_and_caches(auth_client):
    """First call generates interactions; second returns from cache."""
    member_id = await _create_member(auth_client)
    await _create_doctor_visit_with_rx(auth_client, member_id, ["Warfarin 5mg", "Aspirin 75mg", "Omeprazole 20mg"])

    with patch("app.services.ai_service.AIService.check_drug_interactions", side_effect=_mock_check_interactions):
        # First call — generates fresh
        resp1 = await auth_client.get(f"/api/v1/members/{member_id}/latest-drug-interactions")
        assert resp1.status_code == 200
        body1 = resp1.json()
        assert len(body1["interactions"]) == 2
        assert body1["medications_checked"] == 3

    # Second call — should hit cache (no AI mock needed)
    resp2 = await auth_client.get(f"/api/v1/members/{member_id}/latest-drug-interactions")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert len(body2["interactions"]) == 2
    assert body2["interactions"][0]["severity"] == "high"


async def test_latest_interactions_cache_scoped_to_member(auth_client):
    """Cache key is per-member — different members don't share results."""
    member_a = await _create_member(auth_client)
    member_b = await _create_member(auth_client)

    await _create_doctor_visit_with_rx(auth_client, member_a, ["Warfarin 5mg", "Aspirin 75mg"])
    await _create_doctor_visit_with_rx(auth_client, member_b, ["Metformin 500mg", "Glimepiride 2mg"])

    mock_interactions_a = [{"drugs": ["Warfarin", "Aspirin"], "severity": "high", "description": "Bleeding", "recommendation": "Monitor"}]
    mock_interactions_b = [{"drugs": ["Metformin", "Glimepiride"], "severity": "low", "description": "Hypoglycemia risk", "recommendation": "Monitor sugar"}]

    call_count = 0

    async def mock_check(medications):
        nonlocal call_count
        call_count += 1
        # Return different results based on medications
        med_names = [m["medicine"] for m in medications]
        if "Warfarin 5mg" in med_names:
            return mock_interactions_a
        return mock_interactions_b

    with patch("app.services.ai_service.AIService.check_drug_interactions", side_effect=mock_check):
        resp_a = await auth_client.get(f"/api/v1/members/{member_a}/latest-drug-interactions")
        resp_b = await auth_client.get(f"/api/v1/members/{member_b}/latest-drug-interactions")

    assert resp_a.json()["interactions"][0]["severity"] == "high"
    assert resp_b.json()["interactions"][0]["severity"] == "low"
    assert call_count == 2


async def test_latest_interactions_ai_failure_returns_empty(auth_client):
    """If AI fails, returns empty list (graceful degradation)."""
    member_id = await _create_member(auth_client)
    await _create_doctor_visit_with_rx(auth_client, member_id, ["Lisinopril 10mg", "Amlodipine 5mg"])

    with patch("app.services.ai_service.AIService.check_drug_interactions", new_callable=AsyncMock, side_effect=RuntimeError("AI unavailable")):
        resp = await auth_client.get(f"/api/v1/members/{member_id}/latest-drug-interactions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["interactions"] == []
        assert body["medications_checked"] == 2


async def test_latest_interactions_no_medications_at_all(auth_client):
    """Member with zero records → empty interactions."""
    member_id = await _create_member(auth_client)

    resp = await auth_client.get(f"/api/v1/members/{member_id}/latest-drug-interactions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["interactions"] == []
    assert body["medications_checked"] == 0


# ── GET /{member_id}/drug-interactions (fresh, no cache) ─────────────


async def test_fresh_interactions_member_not_found(auth_client):
    """404 for non-existent member."""
    from uuid import uuid4
    fake_id = str(uuid4())
    resp = await auth_client.get(f"/api/v1/members/{fake_id}/drug-interactions")
    assert resp.status_code == 404


async def test_fresh_interactions_under_2_medications(auth_client):
    """Returns empty when < 2 active medications."""
    member_id = await _create_member(auth_client)
    await _create_doctor_visit_with_rx(auth_client, member_id, ["Metformin 500mg"])

    resp = await auth_client.get(f"/api/v1/members/{member_id}/drug-interactions")
    assert resp.status_code == 200
    assert resp.json()["interactions"] == []


async def test_fresh_interactions_calls_ai_every_time(auth_client):
    """Fresh endpoint calls AI each time — no caching."""
    member_id = await _create_member(auth_client)
    await _create_doctor_visit_with_rx(auth_client, member_id, ["Lisinopril 10mg", "Amlodipine 5mg"])

    call_count = 0

    async def mock_check(medications):
        nonlocal call_count
        call_count += 1
        return [{"drugs": ["Lisinopril", "Amlodipine"], "severity": "low", "description": f"Call {call_count}", "recommendation": "Monitor"}]

    with patch("app.services.ai_service.AIService.check_drug_interactions", side_effect=mock_check):
        resp1 = await auth_client.get(f"/api/v1/members/{member_id}/drug-interactions")
        resp2 = await auth_client.get(f"/api/v1/members/{member_id}/drug-interactions")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert call_count == 2  # Called twice — no caching


async def test_fresh_interactions_ai_failure_returns_empty(auth_client):
    """AI failure → graceful empty response."""
    member_id = await _create_member(auth_client)
    await _create_doctor_visit_with_rx(auth_client, member_id, ["Lisinopril 10mg", "Amlodipine 5mg"])

    with patch("app.services.ai_service.AIService.check_drug_interactions", new_callable=AsyncMock, side_effect=RuntimeError("timeout")):
        resp = await auth_client.get(f"/api/v1/members/{member_id}/drug-interactions")
        assert resp.status_code == 200
        assert resp.json()["interactions"] == []


async def test_fresh_interactions_with_valid_medications(auth_client):
    """Returns interactions for member with >= 2 medications."""
    member_id = await _create_member(auth_client)
    await _create_doctor_visit_with_rx(auth_client, member_id, ["Warfarin 5mg", "Aspirin 75mg"])

    with patch("app.services.ai_service.AIService.check_drug_interactions", side_effect=_mock_check_interactions):
        resp = await auth_client.get(f"/api/v1/members/{member_id}/drug-interactions")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["interactions"]) == 2
        assert body["medications_checked"] == 2


# ── Cache expiry behavior ────────────────────────────────────────────


async def test_latest_interactions_expired_cache_regenerates(auth_client, db_session):
    """Cache older than 24h is ignored and fresh results are generated."""
    from app.models.ai import AIInsight

    member_id = await _create_member(auth_client)
    await _create_doctor_visit_with_rx(auth_client, member_id, ["Lisinopril 10mg", "Amlodipine 5mg"])

    # Insert a stale cache entry (> 24h old)
    stale_insight = AIInsight(
        prompt=f"__drug_interactions__{member_id}",
        response=json.dumps([{"drugs": ["STALE"], "severity": "low", "description": "old", "recommendation": "old"}]),
        provider_used="auto",
        generated_at=datetime.now(timezone.utc) - timedelta(hours=48),
    )
    db_session.add(stale_insight)
    await db_session.commit()

    async def mock_check(medications):
        return [{"drugs": ["Lisinopril", "Amlodipine"], "severity": "high", "description": "fresh", "recommendation": "fresh"}]

    with patch("app.services.ai_service.AIService.check_drug_interactions", side_effect=mock_check):
        resp = await auth_client.get(f"/api/v1/members/{member_id}/latest-drug-interactions")
        assert resp.status_code == 200
        body = resp.json()
        # Should get fresh results, not stale
        assert body["interactions"][0]["description"] == "fresh"


async def test_latest_interactions_malformed_cache_regenerates(auth_client, db_session):
    """Malformed cached JSON is ignored and fresh results generated."""
    from app.models.ai import AIInsight

    member_id = await _create_member(auth_client)
    await _create_doctor_visit_with_rx(auth_client, member_id, ["Lisinopril 10mg", "Amlodipine 5mg"])

    # Insert malformed cache
    bad_cache = AIInsight(
        prompt=f"__drug_interactions__{member_id}",
        response="NOT VALID JSON {{{",
        provider_used="auto",
    )
    db_session.add(bad_cache)
    await db_session.commit()

    async def mock_check(medications):
        return [{"drugs": ["Lisinopril", "Amlodipine"], "severity": "moderate", "description": "regenerated", "recommendation": "check"}]

    with patch("app.services.ai_service.AIService.check_drug_interactions", side_effect=mock_check):
        resp = await auth_client.get(f"/api/v1/members/{member_id}/latest-drug-interactions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["interactions"][0]["description"] == "regenerated"
