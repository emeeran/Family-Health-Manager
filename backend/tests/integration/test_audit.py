"""Integration tests for audit log endpoints."""
import pytest

pytestmark = pytest.mark.asyncio


async def test_list_audit_logs(auth_client):
    """List audit logs returns a list (may be empty for new household)."""
    resp = await auth_client.get("/api/v1/audit-logs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
