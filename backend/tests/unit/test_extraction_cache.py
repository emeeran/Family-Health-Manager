"""Phase 1 — extraction result cache keyed on content hash + version.

A re-upload or duplicate file must be served from cache without re-running the
underlying OCR + LLM extraction. Bumping the version invalidates all entries.
"""

import pytest

from app.core.cache import cache
from app.schemas.health_record import ExtractedFields
from app.services.ai import AIService
from app.services.ai.document_extractor import ExtractionResult


@pytest.fixture
def clean_extraction_cache():
    cache.invalidate("extraction:")
    yield
    cache.invalidate("extraction:")


async def test_extract_caches_by_content_hash(monkeypatch, clean_extraction_cache):
    """The underlying extractor runs once; the second call is a cache hit."""
    calls = {"n": 0}
    expected = ExtractionResult(
        extracted=ExtractedFields(diagnosis="Type 2 Diabetes"),
        transcription="raw transcription",
    )

    async def fake_extract(db, file_path, mime, ref, plan=None, on_progress=None):
        calls["n"] += 1
        return expected

    monkeypatch.setattr("app.services.ai.document_extractor.extract_medical_data", fake_extract)

    svc = AIService(db=None)  # db unused — fake_extract ignores it
    content_hash = "a" * 64

    r1 = await svc.extract_medical_data("/tmp/x.pdf", "application/pdf", content_hash=content_hash)
    r2 = await svc.extract_medical_data("/tmp/x.pdf", "application/pdf", content_hash=content_hash)

    assert r1.extracted.diagnosis == "Type 2 Diabetes"  # first call returns the real result
    assert calls["n"] == 1  # underlying extractor invoked exactly once
    assert r2.extracted.diagnosis == "Type 2 Diabetes"
    assert r2.transcription == "raw transcription"  # transcription cached too


async def test_extract_uncached_when_no_content_hash(monkeypatch, clean_extraction_cache):
    """Without a hash there is no cache key — every call re-extracts."""
    calls = {"n": 0}

    async def fake_extract(db, file_path, mime, ref, plan=None, on_progress=None):
        calls["n"] += 1
        return ExtractionResult(extracted=ExtractedFields(diagnosis="x"))

    monkeypatch.setattr("app.services.ai.document_extractor.extract_medical_data", fake_extract)

    svc = AIService(db=None)
    await svc.extract_medical_data("/tmp/x.pdf", "application/pdf")
    await svc.extract_medical_data("/tmp/x.pdf", "application/pdf")
    assert calls["n"] == 2


async def test_cache_version_invalidates(monkeypatch, clean_extraction_cache):
    """A new version key misses the old cache, forcing a fresh extraction."""
    calls = {"n": 0}

    async def fake_extract(db, file_path, mime, ref, plan=None, on_progress=None):
        calls["n"] += 1
        return ExtractionResult(extracted=ExtractedFields(diagnosis="x"))

    monkeypatch.setattr("app.services.ai.document_extractor.extract_medical_data", fake_extract)

    content_hash = "b" * 64

    # Populate cache under the current version, then bump the version module attr.
    svc = AIService(db=None)
    await svc.extract_medical_data("/tmp/x.pdf", "application/pdf", content_hash=content_hash)

    import app.services.ai as ai_pkg

    monkeypatch.setattr(ai_pkg, "EXTRACTION_CACHE_VERSION", "999")
    await svc.extract_medical_data("/tmp/x.pdf", "application/pdf", content_hash=content_hash)

    assert calls["n"] == 2  # version bump → cache miss → re-extract
