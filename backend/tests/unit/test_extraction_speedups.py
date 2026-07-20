"""Tests for the Phase A–D document-processing speedups.

Covers:
* A1 — vision extraction batches run in parallel (cloud) / sequential (local).
* A2 — transcription overlaps extraction (kicked off before batch loop).
* B1 — chunk extraction concurrency is bounded for local Ollama.
* B2 — OCR page renders are reused by vision fallback; extract_pdf_text
  returns (text, page_count) from a single open.
* C1 — transcription goes through _run_provider_chain (sequential by default,
  not custom racing); _race_vision_entries is gone.
* C2 — call_ocr respects per-provider timeout.
* D2 — cache key includes prompt hash; version bump invalidates old entries.

All provider functions are mocked — no network.
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import app.services.ai.document_extractor as dex
import app.services.ai.provider_health as ph
from app.schemas.ai_provider_config import (
    AIProviderConfig,
    ProviderConfigItem,
)
from app.services.ai.document_extractor import ExtractionProviderPlan

JSON_OK = '{"record_type": "lab_report"}'


def _plan(primary: str = "cloud") -> ExtractionProviderPlan:
    cfg = AIProviderConfig(
        providers=[ProviderConfigItem(id=p, enabled=True, model="") for p in
                   ("groq", "openrouter", "gemini", "openai", "ollama")],
        primary_provider=primary,  # type: ignore[arg-type]
    )
    return ExtractionProviderPlan.from_config(cfg)


# ---- A1: vision batch parallelism ----


async def test_vision_batches_run_in_parallel_on_cloud(monkeypatch):
    """Two vision batches fire concurrently on cloud — no sequential wait."""
    monkeypatch.setattr(
        "app.services.ai.document_extractor._fast_cloud_text_available",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(dex.settings, "EXTRACTION_VISION_BATCH_SIZE", 1)

    call_times: list[float] = []

    async def slow_vision(b64, mime, prompt, **_kw):
        call_times.append(time.monotonic())
        await asyncio.sleep(0.1)
        return JSON_OK

    with (
        patch.object(dex, "call_groq_vision", slow_vision),
        patch.object(dex, "call_openrouter_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_groq_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_openrouter_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "extract_pdf_text", lambda fp: (None, 2)),
        patch.object(dex, "ocr_pdf_pages", AsyncMock(return_value=("sparse", [b"p1", b"p2"]))),
        patch.object(dex, "_ocr_quality", lambda t: 0.1),
        patch.object(dex, "_transcribe_via_vision", AsyncMock(return_value="transcript")),
        patch.object(dex, "_heuristic_fallback", lambda r, t, m: r),
    ):
        await dex.extract_medical_data(
            db=None, file_path="fake.pdf", mime_type="application/pdf",
            last_provider_ref=[""], plan=_plan("cloud"),
        )
    # Two pages with batch_size=1 → two batches. If parallel, both start
    # within ~10ms; if sequential, the second starts ~100ms after the first.
    assert len(call_times) == 2
    assert abs(call_times[0] - call_times[1]) < 0.05


async def test_vision_batches_sequential_on_local(monkeypatch):
    """Local Ollama: batches run sequentially (Ollama serializes anyway)."""
    monkeypatch.setattr(
        "app.services.ai.document_extractor._fast_cloud_text_available",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(dex.settings, "EXTRACTION_VISION_BATCH_SIZE", 1)

    call_times: list[float] = []

    async def slow_vision(b64, mime, prompt, **_kw):
        call_times.append(time.monotonic())
        await asyncio.sleep(0.1)
        return JSON_OK

    with (
        patch.object(dex, "call_groq_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_openrouter_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_vision", slow_vision),
        patch.object(dex, "call_groq_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_openrouter_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "extract_pdf_text", lambda fp: (None, 2)),
        patch.object(dex, "ocr_pdf_pages", AsyncMock(return_value=("sparse", [b"p1", b"p2"]))),
        patch.object(dex, "_ocr_quality", lambda t: 0.1),
        patch.object(dex, "_transcribe_via_vision", AsyncMock(return_value="transcript")),
        patch.object(dex, "_heuristic_fallback", lambda r, t, m: r),
    ):
        await dex.extract_medical_data(
            db=None, file_path="fake.pdf", mime_type="application/pdf",
            last_provider_ref=[""], plan=_plan("local"),
        )
    assert len(call_times) == 2
    # Sequential: second starts after first completes (~0.1s gap).
    assert call_times[1] - call_times[0] >= 0.05


# ---- A2: transcription overlaps extraction ----


async def test_transcription_overlaps_vision_extraction(monkeypatch):
    """Transcription task is created before the batch loop and awaited after."""
    monkeypatch.setattr(
        "app.services.ai.document_extractor._fast_cloud_text_available",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(dex.settings, "EXTRACTION_VISION_BATCH_SIZE", 3)

    extract_start: list[float] = []
    transcribe_start: list[float] = []

    async def slow_extract(b64, mime, prompt, **_kw):
        extract_start.append(time.monotonic())
        await asyncio.sleep(0.1)
        return JSON_OK

    async def slow_transcribe(images, mime_type=None, plan=None, **_kw):
        transcribe_start.append(time.monotonic())
        await asyncio.sleep(0.1)
        return "transcript"

    with (
        patch.object(dex, "call_groq_vision", slow_extract),
        patch.object(dex, "call_openrouter_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_groq_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_openrouter_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "extract_pdf_text", lambda fp: (None, 1)),
        patch.object(dex, "ocr_pdf_pages", AsyncMock(return_value=("sparse", [b"p1"]))),
        patch.object(dex, "_ocr_quality", lambda t: 0.1),
        patch.object(dex, "_transcribe_via_vision", slow_transcribe),
        patch.object(dex, "_heuristic_fallback", lambda r, t, m: r),
    ):
        await dex.extract_medical_data(
            db=None, file_path="fake.pdf", mime_type="application/pdf",
            last_provider_ref=[""], plan=_plan("cloud"),
        )
    # Both started within ~10ms — transcription overlapped extraction.
    assert abs(extract_start[0] - transcribe_start[0]) < 0.05


# ---- B1: chunk concurrency bounded for local ----


async def test_chunk_concurrency_bounded_for_local(monkeypatch):
    """Local Ollama: chunk extraction is bounded to 2 concurrent calls."""
    monkeypatch.setattr(
        "app.services.ai.document_extractor._fast_cloud_text_available",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(dex.settings, "EXTRACTION_PAGES_PER_CHUNK", 1)

    concurrent = {"current": 0, "max": 0}
    lock = asyncio.Lock()

    async def tracked_extract(chunk, ref, plan=None):
        async with lock:
            concurrent["current"] += 1
            concurrent["max"] = max(concurrent["max"], concurrent["current"])
        await asyncio.sleep(0.05)
        async with lock:
            concurrent["current"] -= 1
        return JSON_OK

    pages = "\n\n".join(f"--- Page {i} ---\ncontent {i}" for i in range(1, 5))
    with (
        patch.object(dex, "call_text_extraction", tracked_extract),
        patch.object(dex, "extract_pdf_text", lambda fp: (None, 4)),
        patch.object(dex, "ocr_pdf_pages", AsyncMock(return_value=(pages, []))),
        patch.object(dex, "_ocr_quality", lambda t: 0.8),
        patch.object(dex, "_heuristic_fallback", lambda r, t, m: r),
    ):
        await dex.extract_medical_data(
            db=None, file_path="fake.pdf", mime_type="application/pdf",
            last_provider_ref=[""], plan=_plan("local"),
        )
    # 4 chunks, bounded to 2 → max concurrent is 2.
    assert concurrent["max"] <= 2


async def test_chunk_concurrency_unbounded_for_cloud(monkeypatch):
    """Cloud: all chunks fire at once (no artificial cap)."""
    monkeypatch.setattr(
        "app.services.ai.document_extractor._fast_cloud_text_available",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(dex.settings, "EXTRACTION_PAGES_PER_CHUNK", 1)

    concurrent = {"current": 0, "max": 0}
    lock = asyncio.Lock()

    async def tracked_extract(chunk, ref, plan=None):
        async with lock:
            concurrent["current"] += 1
            concurrent["max"] = max(concurrent["max"], concurrent["current"])
        await asyncio.sleep(0.05)
        async with lock:
            concurrent["current"] -= 1
        return JSON_OK

    pages = "\n\n".join(f"--- Page {i} ---\ncontent {i}" for i in range(1, 5))
    with (
        patch.object(dex, "call_text_extraction", tracked_extract),
        patch.object(dex, "_format_ocr_transcription", AsyncMock(return_value="formatted")),
        patch.object(dex, "extract_pdf_text", lambda fp: (None, 4)),
        patch.object(dex, "ocr_pdf_pages", AsyncMock(return_value=(pages, []))),
        patch.object(dex, "_ocr_quality", lambda t: 0.8),
        patch.object(dex, "_heuristic_fallback", lambda r, t, m: r),
    ):
        await dex.extract_medical_data(
            db=None, file_path="fake.pdf", mime_type="application/pdf",
            last_provider_ref=[""], plan=_plan("cloud"),
        )
    # 4 chunks, all fire at once on cloud.
    assert concurrent["max"] == 4


# ---- B2: OCR renders reused + extract_pdf_text returns tuple ----


def test_extract_pdf_text_returns_tuple():
    """extract_pdf_text returns (text, page_count) from a single open."""
    import os
    import tempfile

    import fitz

    doc = fitz.open()  # new empty doc
    doc.new_page()
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    doc.save(tmp.name)
    doc.close()

    text, page_count = dex.extract_pdf_text(tmp.name)
    assert page_count == 1
    # Empty page → text is None.
    assert text is None or text == ""

    os.unlink(tmp.name)


async def test_vision_fallback_reuses_ocr_renders(monkeypatch):
    """When OCR ran, the vision fallback reuses its page renders (no re-render)."""
    monkeypatch.setattr(
        "app.services.ai.document_extractor._fast_cloud_text_available",
        AsyncMock(return_value=True),
    )

    render_calls: list[int] = []
    fake_renders = [b"page0_png", b"page1_png"]

    with (
        patch.object(dex, "call_groq_vision", AsyncMock(return_value=JSON_OK)),
        patch.object(dex, "call_openrouter_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_groq_vision_multi", AsyncMock(return_value=JSON_OK)),
        patch.object(dex, "call_openrouter_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "extract_pdf_text", lambda fp: (None, 2)),
        patch.object(dex, "ocr_pdf_pages", AsyncMock(return_value=("sparse text", fake_renders))),
        patch.object(dex, "_ocr_quality", lambda t: 0.1),
        patch.object(dex, "pdf_page_to_image", lambda fp, pn: render_calls.append(pn) or b"img"),
        patch.object(dex, "_transcribe_via_vision", AsyncMock(return_value="t")),
        patch.object(dex, "_heuristic_fallback", lambda r, t, m: r),
    ):
        await dex.extract_medical_data(
            db=None, file_path="fake.pdf", mime_type="application/pdf",
            last_provider_ref=[""], plan=_plan("cloud"),
        )
    # pdf_page_to_image was NOT called — OCR renders were reused.
    assert render_calls == []


async def test_vision_fallback_renders_when_no_ocr_renders(monkeypatch):
    """When OCR didn't produce renders (tesseract absent), vision renders pages."""
    monkeypatch.setattr(
        "app.services.ai.document_extractor._fast_cloud_text_available",
        AsyncMock(return_value=True),
    )

    render_calls: list[int] = []

    with (
        patch.object(dex, "call_groq_vision", AsyncMock(return_value=JSON_OK)),
        patch.object(dex, "call_openrouter_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_groq_vision_multi", AsyncMock(return_value=JSON_OK)),
        patch.object(dex, "call_openrouter_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "extract_pdf_text", lambda fp: (None, 2)),
        patch.object(dex, "ocr_pdf_pages", AsyncMock(return_value=(None, []))),
        patch.object(dex, "_ocr_quality", lambda t: 0.0),
        patch.object(dex, "pdf_page_to_image", lambda fp, pn: render_calls.append(pn) or b"img"),
        patch.object(dex, "_transcribe_via_vision", AsyncMock(return_value="t")),
        patch.object(dex, "_heuristic_fallback", lambda r, t, m: r),
    ):
        await dex.extract_medical_data(
            db=None, file_path="fake.pdf", mime_type="application/pdf",
            last_provider_ref=[""], plan=_plan("cloud"),
        )
    # pdf_page_to_image WAS called — no cached renders to reuse.
    assert len(render_calls) == 2


# ---- C1: transcription through the chain ----


async def test_format_ocr_transcription_uses_chain_not_racing():
    """_format_ocr_transcription goes through _run_provider_chain (sequential)."""
    call_order: list[str] = []

    async def groq(prompt):
        call_order.append("groq")
        return "formatted"

    with (
        patch.object(dex, "call_groq_text", groq),
        patch.object(dex, "call_openrouter_text", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_text", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_text", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_text", AsyncMock(return_value=None)),
    ):
        result = await dex._format_ocr_transcription(
            "some raw OCR text that is long enough", [""], _plan("cloud")
        )
    assert result == "formatted"
    # Sequential: Groq (first in plan) won, OpenRouter was never called.
    assert call_order == ["groq"]


async def test_transcribe_via_vision_uses_chain_not_racing(monkeypatch):
    """_transcribe_via_vision uses _run_provider_chain (sequential, not racing)."""
    call_order: list[str] = []

    async def groq_multi(images, mime, prompt, **_kw):
        call_order.append("groq_multi")
        return "transcript"

    monkeypatch.setattr(dex.settings, "EXTRACTION_VISION_BATCH_SIZE", 3)
    with (
        patch.object(dex, "call_groq_vision_multi", groq_multi),
        patch.object(dex, "call_openrouter_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_vision_multi", AsyncMock(return_value=None)),
    ):
        result = await dex._transcribe_via_vision(
            ["p1", "p2", "p3"], "image/png", plan=_plan("cloud")
        )
    assert result == "transcript"
    # Sequential: Groq won, OpenRouter was never called.
    assert call_order == ["groq_multi"]


def test_race_vision_entries_removed():
    """_race_vision_entries has been removed (replaced by _run_provider_chain)."""
    assert not hasattr(dex, "_race_vision_entries")


# ---- C2: call_ocr timeout ----


async def test_call_ocr_times_out_on_slow_provider(monkeypatch):
    """call_ocr respects EXTRACTION_PROVIDER_TIMEOUT — a slow cloud OCR fails fast."""
    monkeypatch.setattr(dex.settings, "EXTRACTION_PROVIDER_TIMEOUT", 0.1)

    async def slow_gemini_ocr(b64, mime, model=None, gemini_auth="auto"):
        await asyncio.sleep(1.0)
        return "ocr text"

    async def fast_ollama_ocr(b64, mime):
        return "ollama ocr text"

    cfg = AIProviderConfig(
        providers=[
            ProviderConfigItem(id="gemini", enabled=True, model=""),
            ProviderConfigItem(id="ollama", enabled=True, model=""),
        ],
        primary_provider="cloud",  # type: ignore[arg-type]
    )
    plan = ExtractionProviderPlan.from_config(cfg)

    with (
        patch.object(dex, "call_gemini_ocr", slow_gemini_ocr),
        patch.object(dex, "call_ollama_ocr", fast_ollama_ocr),
        patch("pathlib.Path.read_bytes", return_value=b"img"),
    ):
        result = await dex.call_ocr("fake.png", "image/png", plan)
    # Gemini timed out → Ollama was tried as fallback.
    assert result == "ollama ocr text"


async def test_call_ocr_catches_provider_exception():
    """call_ocr catches exceptions and falls through to the next provider."""

    async def failing_gemini(b64, mime, model=None, gemini_auth="auto"):
        raise RuntimeError("key invalid")

    async def working_ollama(b64, mime):
        return "ollama text"

    cfg = AIProviderConfig(
        providers=[
            ProviderConfigItem(id="gemini", enabled=True, model=""),
            ProviderConfigItem(id="ollama", enabled=True, model=""),
        ],
        primary_provider="cloud",  # type: ignore[arg-type]
    )
    plan = ExtractionProviderPlan.from_config(cfg)

    with (
        patch.object(dex, "call_gemini_ocr", failing_gemini),
        patch.object(dex, "call_ollama_ocr", working_ollama),
        patch("pathlib.Path.read_bytes", return_value=b"img"),
    ):
        result = await dex.call_ocr("fake.png", "image/png", plan)
    assert result == "ollama text"


# ---- D2: prompt hash in cache key ----


def test_prompt_hash_is_stable():
    """EXTRACTION_PROMPT_HASH is a stable 8-char hex string."""
    assert isinstance(dex.EXTRACTION_PROMPT_HASH, str)
    assert len(dex.EXTRACTION_PROMPT_HASH) == 8
    # Re-computing gives the same value.
    assert dex._prompt_hash() == dex.EXTRACTION_PROMPT_HASH


async def test_cache_key_includes_prompt_hash(monkeypatch):
    """The cache key includes the prompt hash — editing the prompt invalidates."""
    from app.services.ai import AIService
    from app.services.ai.document_extractor import ExtractionResult
    from app.schemas.health_record import ExtractedFields

    ph.clear()
    monkeypatch.setattr("app.core.provider_keys.any_cloud_provider_configured", _afalse)
    store: dict = {}
    _install_fake_cache(monkeypatch, store)

    calls = {"n": 0}

    async def fake_extract(db, fp, mt, ref, plan=None, on_progress=None):
        calls["n"] += 1
        return ExtractionResult(extracted=ExtractedFields(diagnosis="x"))

    monkeypatch.setattr(
        "app.services.ai.document_extractor.extract_medical_data", fake_extract
    )

    svc = AIService(db=None)
    await svc.extract_medical_data("x.pdf", "application/pdf", content_hash="h1")

    # Mutate the prompt hash to simulate a prompt edit → cache should miss.
    original_hash = dex.EXTRACTION_PROMPT_HASH
    monkeypatch.setattr(dex, "EXTRACTION_PROMPT_HASH", "deadbeef")
    try:
        await svc.extract_medical_data("x.pdf", "application/pdf", content_hash="h1")
    finally:
        monkeypatch.setattr(dex, "EXTRACTION_PROMPT_HASH", original_hash)

    assert calls["n"] == 2  # re-extracted because the prompt hash changed


def test_cache_version_bumped():
    """EXTRACTION_CACHE_VERSION is '5' (bumped for the prompt-hash key change)."""
    from app.services.ai import EXTRACTION_CACHE_VERSION
    assert EXTRACTION_CACHE_VERSION == "5"


# ---- Deviation 1 fix: EXTRACTION_VISION_BATCH_CONCURRENCY cap ----


async def test_vision_batch_concurrency_capped_on_cloud(monkeypatch):
    """Cloud vision batches are capped at EXTRACTION_VISION_BATCH_CONCURRENCY."""
    monkeypatch.setattr(
        "app.services.ai.document_extractor._fast_cloud_text_available",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(dex.settings, "EXTRACTION_VISION_BATCH_SIZE", 1)
    monkeypatch.setattr(dex.settings, "EXTRACTION_VISION_BATCH_CONCURRENCY", 2)

    concurrent = {"current": 0, "max": 0}
    lock = asyncio.Lock()

    async def tracked_vision(b64, mime, prompt, **_kw):
        async with lock:
            concurrent["current"] += 1
            concurrent["max"] = max(concurrent["max"], concurrent["current"])
        await asyncio.sleep(0.05)
        async with lock:
            concurrent["current"] -= 1
        return JSON_OK

    with (
        patch.object(dex, "call_groq_vision", tracked_vision),
        patch.object(dex, "call_openrouter_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_groq_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_openrouter_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "extract_pdf_text", lambda fp: (None, 6)),
        patch.object(dex, "ocr_pdf_pages", AsyncMock(return_value=("sparse", [b"p"] * 6))),
        patch.object(dex, "_ocr_quality", lambda t: 0.1),
        patch.object(dex, "_png_to_jpeg", lambda png: b"jpeg"),
        patch.object(dex, "_transcribe_via_vision", AsyncMock(return_value="t")),
        patch.object(dex, "_heuristic_fallback", lambda r, t, m: r),
    ):
        await dex.extract_medical_data(
            db=None, file_path="fake.pdf", mime_type="application/pdf",
            last_provider_ref=[""], plan=_plan("cloud"),
        )
    # 6 pages / batch_size=1 = 6 batches, capped at 2 → max concurrent is 2.
    assert concurrent["max"] <= 2


# ---- Deviation 2 fix: PNG re-encoded to JPEG ----


def test_png_to_jpeg_reduces_size():
    """_png_to_jpeg produces valid JPEG bytes smaller than the PNG input.

    Uses a noisy image (like a real rendered PDF page with text) where JPEG's
    lossy compression wins over PNG. A solid-color image would compress better
    as PNG, which isn't representative of document renders.
    """
    import io
    import random

    from PIL import Image

    random.seed(42)
    # 200x200 with per-pixel noise — simulates a document with text/content.
    img = Image.new("RGB", (200, 200))
    pixels = img.load()
    for y in range(200):
        for x in range(200):
            pixels[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    png_buf = io.BytesIO()
    img.save(png_buf, format="PNG")
    png_bytes = png_buf.getvalue()

    jpeg_bytes = dex._png_to_jpeg(png_bytes)
    assert len(jpeg_bytes) < len(png_bytes)
    # JPEG magic bytes.
    assert jpeg_bytes[:2] == b"\xff\xd8"


def test_png_to_jpeg_falls_back_on_error():
    """_png_to_jpeg returns the original bytes when PIL can't decode."""
    garbage = b"not an image"
    result = dex._png_to_jpeg(garbage)
    assert result == garbage


async def test_vision_fallback_re_encodes_renders_to_jpeg(monkeypatch):
    """OCR PNG renders are re-encoded to JPEG before base64-encoding for vision."""
    monkeypatch.setattr(
        "app.services.ai.document_extractor._fast_cloud_text_available",
        AsyncMock(return_value=True),
    )

    reencoded: list[bytes] = []
    original_pngs = [b"page0_png", b"page1_png"]

    def fake_reencode(png):
        reencoded.append(png)
        return b"jpeg_" + png  # deterministic transform so we can verify it was called

    with (
        patch.object(dex, "call_groq_vision", AsyncMock(return_value=JSON_OK)),
        patch.object(dex, "call_openrouter_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_vision", AsyncMock(return_value=None)),
        patch.object(dex, "call_groq_vision_multi", AsyncMock(return_value=JSON_OK)),
        patch.object(dex, "call_openrouter_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "extract_pdf_text", lambda fp: (None, 2)),
        patch.object(dex, "ocr_pdf_pages", AsyncMock(return_value=("sparse", original_pngs))),
        patch.object(dex, "_ocr_quality", lambda t: 0.1),
        patch.object(dex, "_png_to_jpeg", fake_reencode),
        patch.object(dex, "pdf_page_to_image", lambda fp, pn: b"should_not_be_called"),
        patch.object(dex, "_transcribe_via_vision", AsyncMock(return_value="t")),
        patch.object(dex, "_heuristic_fallback", lambda r, t, m: r),
    ):
        await dex.extract_medical_data(
            db=None, file_path="fake.pdf", mime_type="application/pdf",
            last_provider_ref=[""], plan=_plan("cloud"),
        )
    # Both PNG renders were re-encoded through _png_to_jpeg.
    assert reencoded == original_pngs


# ---- Deviation 3 fix: preprocess parameter ----


def test_preprocess_image_for_ocr_skips_when_disabled(tmp_path):
    """preprocess=False returns None immediately — no PIL pipeline."""
    # Create a real image file so the function *could* open it if not skipped.
    from PIL import Image

    img = Image.new("RGB", (10, 10), color=(0, 0, 0))
    img.save(str(tmp_path / "test.png"), format="PNG")

    result = dex._preprocess_image_for_ocr(str(tmp_path / "test.png"), preprocess=False)
    assert result is None


def test_preprocess_image_for_ocr_runs_when_enabled(tmp_path):
    """preprocess=True (default) runs the PIL pipeline and returns a temp path."""
    from PIL import Image

    img = Image.new("RGB", (10, 10), color=(0, 0, 0))
    img.save(str(tmp_path / "test.png"), format="PNG")

    result = dex._preprocess_image_for_ocr(str(tmp_path / "test.png"), preprocess=True)
    assert result is not None
    # The enhanced image is a temp file.
    import os

    assert os.path.exists(result)
    os.unlink(result)


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
