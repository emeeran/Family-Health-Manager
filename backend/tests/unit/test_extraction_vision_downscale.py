"""Tests for raw-image downscaling before vision payloads (speedup #1).

Phone photos of documents are uploaded at ~4000px / multi-MB and were sent raw
to every vision call. ``_downscale_for_vision`` caps the longest side and
re-encodes as JPEG so the payload shrinks ~10-20x with no loss of medical
legibility. PDF pages are already DPI-bounded; this only touches raw image
uploads (the ``image/*`` OCR-via-LLM path and the image vision-only path).
"""

import base64
import io
from unittest.mock import AsyncMock, patch

import app.services.ai.document_extractor as dex
from app.schemas.ai_provider_config import AIProviderConfig, ProviderConfigItem
from app.services.ai.document_extractor import ExtractionProviderPlan

JSON_OK = '{"record_type": "lab_report"}'


def _plan() -> ExtractionProviderPlan:
    cfg = AIProviderConfig(
        providers=[
            ProviderConfigItem(id=p, enabled=True, model="")
            for p in ("groq", "openrouter", "gemini", "openai", "ollama")
        ],
        primary_provider="cloud",  # type: ignore[arg-type]
    )
    return ExtractionProviderPlan.from_config(cfg)


def _png_bytes(size: tuple[int, int], mode: str = "RGB") -> bytes:
    from PIL import Image

    img = Image.new(mode, size, color=(123, 45, 67) if mode == "RGB" else (123, 45, 67, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---- _downscale_for_vision unit tests ----


def test_downscale_caps_large_image():
    """A large image is capped to EXTRACTION_VISION_MAX_DIM and emitted as JPEG."""
    from PIL import Image

    out_bytes, out_mime = dex._downscale_for_vision(_png_bytes((4000, 3000)), "image/png")
    assert out_mime == "image/jpeg"
    assert out_bytes[:2] == b"\xff\xd8"  # JPEG magic bytes
    # thumbnail preserves aspect ratio and only shrinks → longest side <= 1568
    assert max(Image.open(io.BytesIO(out_bytes)).size) <= 1568


def test_downscale_does_not_upscale_small_image():
    """A small image is re-encoded as JPEG but its dimensions are unchanged."""
    from PIL import Image

    out_bytes, out_mime = dex._downscale_for_vision(_png_bytes((400, 300)), "image/png")
    assert out_mime == "image/jpeg"
    assert Image.open(io.BytesIO(out_bytes)).size == (400, 300)


def test_downscale_falls_back_on_garbage():
    """Non-image bytes fall back to the original (bytes, mime) — never strands a doc."""
    garbage = b"definitely not an image"
    out_bytes, out_mime = dex._downscale_for_vision(garbage, "image/png")
    assert out_bytes == garbage
    assert out_mime == "image/png"


def test_downscale_disabled_when_max_dim_zero(monkeypatch):
    """EXTRACTION_VISION_MAX_DIM=0 disables downscaling entirely (returns original)."""
    monkeypatch.setattr(dex.settings, "EXTRACTION_VISION_MAX_DIM", 0)
    raw = _png_bytes((4000, 3000))
    out_bytes, out_mime = dex._downscale_for_vision(raw, "image/png")
    assert out_bytes == raw
    assert out_mime == "image/png"


def test_downscale_flattens_alpha():
    """RGBA / transparent images flatten onto white and emit valid JPEG."""
    from PIL import Image

    out_bytes, out_mime = dex._downscale_for_vision(_png_bytes((100, 100), "RGBA"), "image/png")
    assert out_mime == "image/jpeg"
    Image.open(io.BytesIO(out_bytes))  # does not raise


# ---- integration: call_ocr downscales before encoding ----


async def test_call_ocr_downscales_before_encoding(monkeypatch):
    """call_ocr downscales the upload before base64-encoding the vision payload."""
    raw_png = _png_bytes((4000, 3000))

    captured: dict = {}

    async def fake_gemini_ocr(b64, mime, model=None, gemini_auth="auto"):
        captured["len"] = len(base64.b64decode(b64))
        captured["mime"] = mime
        return "ocr text"

    cfg = AIProviderConfig(
        providers=[ProviderConfigItem(id="gemini", enabled=True, model="")],
        primary_provider="cloud",  # type: ignore[arg-type]
    )
    plan = ExtractionProviderPlan.from_config(cfg)

    with (
        patch.object(dex, "call_gemini_ocr", fake_gemini_ocr),
        patch("pathlib.Path.read_bytes", return_value=raw_png),
    ):
        result = await dex.call_ocr("fake.png", "image/png", plan)

    assert result == "ocr text"
    # Payload was downscaled (much smaller than the raw 4000x3000 PNG) + JPEG.
    assert captured["mime"] == "image/jpeg"
    assert captured["len"] < len(raw_png)


# ---- integration: image vision-only path downscales ----


async def test_image_vision_path_downscales(monkeypatch):
    """The image vision-only path downscales before sending to vision + transcription."""
    raw_png = _png_bytes((4000, 3000))

    captured: dict = {}

    async def fake_vision_from_b64(b64, mime, ref, plan=None):
        captured["vlen"] = len(base64.b64decode(b64))
        captured["vmime"] = mime
        return JSON_OK

    async def fake_transcribe(images, mime, plan=None, **_kw):
        captured["tlen"] = len(base64.b64decode(images[0]))
        captured["tmime"] = mime
        return "transcript"

    with (
        patch.object(dex, "tesseract_image", lambda fp: None),  # local OCR empty
        patch.object(dex, "call_ocr", AsyncMock(return_value=None)),  # cloud OCR empty
        patch.object(dex, "call_vision_provider_from_b64", fake_vision_from_b64),
        patch.object(dex, "_transcribe_via_vision", fake_transcribe),
        patch("pathlib.Path.read_bytes", return_value=raw_png),
    ):
        await dex.extract_medical_data(
            db=None,
            file_path="fake.png",
            mime_type="image/png",
            last_provider_ref=[""],
            plan=_plan(),
        )

    assert captured["vmime"] == "image/jpeg"
    assert captured["tmime"] == "image/jpeg"
    assert captured["vlen"] < len(raw_png)
    assert captured["tlen"] < len(raw_png)
