"""Free-text search still works after clinical_data/diagnosis/prescription_text
were Fernet-encrypted at rest — the search now decrypts then filters in Python.

Covers the 3 rewritten call-sites: household records search, smart search
(plaintext fallback path), and member records list `search`.
"""

import pytest

pytestmark = pytest.mark.asyncio

MEMBER_PAYLOAD = {
    "first_name": "Search",
    "last_name": "Patient",
    "date_of_birth": "1990-01-01",
    "gender": "male",
    "relationship": "self",
}


async def _seed(auth_client) -> str:
    member_id = (
        (await auth_client.post("/api/v1/members", json=MEMBER_PAYLOAD)).json()["id"]
    )
    # A record whose clinical_data + diagnosis contain distinctive terms.
    await auth_client.post(
        f"/api/v1/members/{member_id}/records",
        json={
            "record_type": "doctor_visit",
            "record_date": "2026-02-01",
            "clinical_data": "Follow-up for DIABETES mellitus type 2",
            "diagnosis": "Type 2 diabetes",
        },
    )
    # A second, non-matching record.
    await auth_client.post(
        f"/api/v1/members/{member_id}/records",
        json={
            "record_type": "doctor_visit",
            "record_date": "2026-02-02",
            "clinical_data": "Routine annual physical, all normal",
            "diagnosis": "Healthy",
        },
    )
    return member_id


async def test_household_records_search_finds_encrypted_match(auth_client):
    await _seed(auth_client)
    resp = await auth_client.get(
        "/api/v1/household/records/search", params={"q": "diabetes"}
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert "diabetes" in rows[0]["clinical_data"].lower()


async def test_smart_search_fallback_finds_encrypted_match(auth_client):
    """Short query → no AI → plaintext fallback path (now Python-side)."""
    await _seed(auth_client)
    resp = await auth_client.post("/api/v1/smart-search/records", json={"query": "diabetes"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert any("diabetes" in (r.get("diagnosis") or "").lower() for r in body["results"])


async def test_member_records_search_finds_encrypted_match(auth_client):
    member_id = await _seed(auth_client)
    resp = await auth_client.get(
        f"/api/v1/members/{member_id}/records", params={"search": "diabetes"}
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    # List response shape may be paginated; accept either a list or {items:[...]}.
    items = rows if isinstance(rows, list) else rows.get("items", rows.get("records", []))
    assert len(items) == 1
    assert "diabetes" in items[0]["clinical_data"].lower()


async def test_household_search_no_false_positive(auth_client):
    """A term that doesn't appear in plaintext returns nothing (proves the
    match is on decrypted content, not ciphertext noise)."""
    await _seed(auth_client)
    resp = await auth_client.get(
        "/api/v1/household/records/search", params={"q": "zzznotaterm"}
    )
    assert resp.status_code == 200
    assert resp.json() == []
