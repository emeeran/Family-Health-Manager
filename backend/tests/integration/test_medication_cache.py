"""Medication mutations must invalidate the dashboard cache.

Regression for the invalidation-prefix bug: medication handlers invalidated
``dashboard:{member_id}`` (a key that is never set) instead of
``dashboard_summary:{household_id}``, so the 60s dashboard cache served a stale
summary after any add/edit/delete. With the fix the cache is busted and the next
/dashboard/summary recomputes — observable here because add_medication creates a
DOCTOR_VISIT record that then appears in ``recent_records``.
"""


import pytest

pytestmark = pytest.mark.asyncio


MEMBER_PAYLOAD = {
    "first_name": "Cache",
    "last_name": "Patient",
    "date_of_birth": "1990-01-01",
    "gender": "male",
    "relationship": "self",
}


async def test_dashboard_summary_invalidated_after_medication_add(auth_client):
    member = (
        await auth_client.post("/api/v1/members", json=MEMBER_PAYLOAD)
    ).json()["id"]

    # Prime the cache, then capture the pre-mutation record count.
    before = (await auth_client.get("/api/v1/dashboard/summary")).json()
    n_before = len(before.get("recent_records", []))

    resp = await auth_client.post(
        f"/api/v1/members/{member}/medications",
        json={"medicine": "Testazine 50mg"},
    )
    assert resp.status_code == 201, resp.text

    # If the cache key were not invalidated this returns the stale summary
    # (n_after == n_before). The fix busts dashboard_summary:{hh} so the next
    # read recomputes and sees the new DOCTOR_VISIT record.
    after = (await auth_client.get("/api/v1/dashboard/summary")).json()
    n_after = len(after.get("recent_records", []))
    assert n_after == n_before + 1, (
        f"dashboard cache not invalidated by medication add: {n_before} → {n_after}"
    )
