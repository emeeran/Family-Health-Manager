"""HTTP contract tests for previously-untested router surfaces:

- ``GET /ai/status`` (auth gating + response shape; provider probe mocked).
- ``GET /members/{id}/duplicate-therapy`` (the new same-class-overlap endpoint).
"""

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio


async def test_ai_status_requires_auth(client):
    """No token → the household dependency rejects (not 200)."""
    resp = await client.get("/api/v1/ai/status")
    assert resp.status_code in (401, 403, 422)


async def test_ai_status_returns_providers(auth_client):
    """Authenticated call returns {providers: [...]}; the live probe is mocked."""
    fake = AsyncMock(return_value=[{"id": "groq", "available": True}])
    with patch("app.services.ai.provider_health.status_for_endpoint", fake):
        resp = await auth_client.get("/api/v1/ai/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "providers" in body
    assert body["providers"][0]["id"] == "groq"


async def test_duplicate_therapy_endpoint_shape(auth_client):
    """A member with no meds returns an empty findings list (contract shape)."""
    create = await auth_client.post(
        "/api/v1/members",
        json={
            "first_name": "Dupe",
            "last_name": "Test",
            "date_of_birth": "1990-01-01",
            "gender": "male",
            "relationship": "self",
        },
    )
    assert create.status_code == 201, create.text
    member_id = create.json()["id"]

    resp = await auth_client.get(f"/api/v1/members/{member_id}/duplicate-therapy")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["findings"] == []
    assert body["medications_checked"] == 0


async def test_duplicate_therapy_unknown_member_404(auth_client):
    resp = await auth_client.get(
        "/api/v1/members/00000000-0000-0000-0000-000000000000/duplicate-therapy"
    )
    assert resp.status_code == 404
