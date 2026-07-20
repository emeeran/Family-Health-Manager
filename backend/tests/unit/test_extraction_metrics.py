"""Tests for the extraction measurement harness (speedup #4).

The ring buffer + summary aggregate per-extraction signals (latency, cache hit,
data rate, provider/mime mix) so prompt-trim / fast-model / downscale changes
can be validated instead of guessed. Also covers the AIService instrumentation
(miss + cache hit) that feeds it.
"""

from app.services.ai import extraction_metrics as em


def test_summary_empty_when_no_records():
    em.clear()
    s = em.metrics_summary()
    assert s["sample_size"] == 0
    assert s["cache_hit_rate"] is None
    assert s["latency_ms"]["p50"] is None
    assert s["recent"] == []


def test_record_and_summary_aggregates():
    em.clear()
    em.record_extraction(
        mime="application/pdf", provider="Groq", cache_hit=False, had_data=True, elapsed_ms=100
    )
    em.record_extraction(
        mime="application/pdf", provider="Groq", cache_hit=True, had_data=True, elapsed_ms=5
    )
    em.record_extraction(
        mime="image/png", provider="-", cache_hit=False, had_data=False, elapsed_ms=2000
    )
    s = em.metrics_summary()
    assert s["sample_size"] == 3
    assert s["cache_hit_rate"] == round(1 / 3, 3)
    assert s["data_rate"] == round(2 / 3, 3)
    assert s["by_provider"] == {"Groq": 2, "-": 1}
    assert s["by_mime"] == {"application/pdf": 2, "image/png": 1}
    assert s["latency_ms"]["max"] == 2000


def test_percentile_p50_p95():
    em.clear()
    for ms in (10, 20, 30, 40, 100):
        em.record_extraction(elapsed_ms=ms)
    s = em.metrics_summary()
    # nearest-rank: p50 -> 3rd value (30), p95 -> 5th value (100)
    assert s["latency_ms"]["p50"] == 30
    assert s["latency_ms"]["p95"] == 100
    assert s["latency_ms"]["max"] == 100


def test_ring_buffer_caps_at_max():
    em.clear()
    for i in range(250):
        em.record_extraction(elapsed_ms=i)
    assert em.metrics_summary()["sample_size"] == 200


def test_record_never_raises():
    em.clear()
    em.record_extraction()  # no fields
    em.record_extraction(elapsed_ms=None, provider=None)  # None values
    assert em.metrics_summary()["sample_size"] == 2


async def test_extract_records_metric_on_miss_then_hit(monkeypatch):
    """AIService.extract_medical_data records on miss and on cache hit."""
    from app.services.ai import AIService
    from app.services.ai import provider_health as ph
    from app.services.ai.document_extractor import ExtractionResult
    from app.schemas.health_record import ExtractedFields

    em.clear()
    ph.clear()
    monkeypatch.setattr("app.core.provider_keys.any_cloud_provider_configured", _afalse)
    store: dict = {}
    _install_fake_cache(monkeypatch, store)

    async def fake_extract(db, fp, mt, ref, plan=None, on_progress=None):
        return ExtractionResult(extracted=ExtractedFields(diagnosis="x"))

    monkeypatch.setattr(
        "app.services.ai.document_extractor.extract_medical_data", fake_extract
    )

    svc = AIService(db=None)
    await svc.extract_medical_data("x.pdf", "application/pdf", content_hash="h1")  # miss
    await svc.extract_medical_data("x.pdf", "application/pdf", content_hash="h1")  # hit

    s = em.metrics_summary()
    assert s["sample_size"] == 2
    assert s["cache_hit_rate"] == 0.5
    assert s["by_mime"] == {"application/pdf": 2}
    # The miss recorded the (fake) provider + had_data; the hit recorded "-".
    assert s["data_rate"] == 1.0


# ---- helpers ----


async def _afalse(*_a, **_k):
    return False


def _install_fake_cache(monkeypatch, store: dict):
    async def fake_get(key):
        return store.get(key)

    async def fake_set(key, val, ttl=None):
        store[key] = val

    monkeypatch.setattr("app.core.cache.cache.get_async", fake_get)
    monkeypatch.setattr("app.core.cache.cache.set_async", fake_set)
