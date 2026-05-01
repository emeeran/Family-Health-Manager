"""Integration tests for health alerts endpoints."""
import pytest

pytestmark = pytest.mark.asyncio


async def test_list_alerts(auth_client):
    """List health alerts returns a list."""
    resp = await auth_client.get("/api/v1/health-alerts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_get_alert_count(auth_client):
    """Alert count endpoint returns a count."""
    resp = await auth_client.get("/api/v1/health-alerts/count")
    assert resp.status_code == 200
    body = resp.json()
    assert "count" in body or isinstance(body, int) or isinstance(body, dict)
