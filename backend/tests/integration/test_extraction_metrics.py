"""Integration tests for the /ai/extraction-metrics endpoint (speedup #4)."""

import pytest

from app.services.ai import extraction_metrics as em

pytestmark = pytest.mark.asyncio

METRICS_PATH = "/api/v1/ai/extraction-metrics"


async def test_extraction_metrics_endpoint_returns_summary(auth_client):
    em.clear()
    em.record_extraction(
        mime="application/pdf", provider="Groq", cache_hit=False, had_data=True, elapsed_ms=123
    )
    resp = await auth_client.get(METRICS_PATH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["sample_size"] == 1
    assert body["latency_ms"]["max"] == 123
    assert body["by_mime"] == {"application/pdf": 1}


async def test_extraction_metrics_endpoint_empty(auth_client):
    em.clear()
    resp = await auth_client.get(METRICS_PATH)
    assert resp.status_code == 200
    assert resp.json()["sample_size"] == 0


async def test_extraction_metrics_requires_auth(client):
    resp = await client.get(METRICS_PATH)
    assert resp.status_code in (401, 403)
