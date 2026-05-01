"""Integration tests for reminders."""
import pytest
from datetime import datetime, timedelta, timezone


pytestmark = pytest.mark.asyncio

REMINDER_PAYLOAD = {
    "reminder_type": "appointment",
    "title": "Dentist visit",
    "description": "Regular checkup",
    "schedule_type": "once",
    "start_datetime": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
}


async def test_create_reminder(auth_client):
    """Create a reminder returns 201."""
    resp = await auth_client.post("/api/v1/reminders", json=REMINDER_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Dentist visit"
    assert body["reminder_type"] == "appointment"
    assert body["schedule_type"] == "once"
    assert body["is_active"] is True


async def test_list_reminders(auth_client):
    """List reminders returns the created reminder."""
    await auth_client.post("/api/v1/reminders", json=REMINDER_PAYLOAD)
    resp = await auth_client.get("/api/v1/reminders")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1


async def test_update_reminder(auth_client):
    """Update a reminder returns 200 with updated title."""
    create_resp = await auth_client.post("/api/v1/reminders", json=REMINDER_PAYLOAD)
    reminder_id = create_resp.json()["id"]

    resp = await auth_client.put(
        f"/api/v1/reminders/{reminder_id}",
        json={"title": "Dentist visit - rescheduled"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Dentist visit - rescheduled"
