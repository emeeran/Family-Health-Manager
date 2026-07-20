"""Tests for cloud max_tokens capping on extraction calls (speedup #2).

Cloud extraction payloads previously set ``temperature`` but no token cap — a
model could over-generate (the cloud analog of the qwen3 thinking-loop fixed
locally). Extraction now passes ``EXTRACTION_MAX_TOKENS`` (default 2048) to
cloud text/vision entries; Ollama is skipped (already capped via num_predict)
and OCR/transcription are left uncapped.
"""

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


def _kw(entry) -> dict:
    """Bound kwargs of a (possibly bare) entry callable."""
    return getattr(entry.fn, "keywords", {}) or {}


# ---- plan threading ----


def test_text_entries_thread_max_tokens_to_cloud_only():
    """max_tokens reaches every cloud entry's bound kwargs; ollama is skipped."""
    entries = _plan().text_entries(json_grammar=True, max_tokens=2048)
    by_func = {getattr(e.fn, "func", e.fn).__name__: _kw(e) for e in entries}
    assert by_func["call_groq_text"].get("max_tokens") == 2048
    assert by_func["call_openrouter_text"].get("max_tokens") == 2048
    assert by_func["call_gemini_text"].get("max_tokens") == 2048
    assert by_func["call_openai_text"].get("max_tokens") == 2048
    # ollama uses num_predict internally — never receives max_tokens.
    assert "max_tokens" not in by_func["call_ollama_text"]


def test_vision_entries_thread_max_tokens_to_cloud_only():
    entries = _plan().vision_entries(json_grammar=True, max_tokens=2048)
    by_func = {getattr(e.fn, "func", e.fn).__name__: _kw(e) for e in entries}
    assert by_func["call_groq_vision"].get("max_tokens") == 2048
    assert by_func["call_gemini_vision"].get("max_tokens") == 2048
    assert "max_tokens" not in by_func["call_ollama_vision"]


def test_vision_multi_entries_thread_max_tokens_to_cloud_only():
    entries = _plan().vision_multi_entries(json_grammar=True, max_tokens=2048)
    by_func = {getattr(e.fn, "func", e.fn).__name__: _kw(e) for e in entries}
    assert by_func["call_openai_vision_multi"].get("max_tokens") == 2048
    assert "max_tokens" not in by_func["call_ollama_vision_multi"]


def test_text_entries_omit_max_tokens_by_default():
    """Without max_tokens, no entry carries it."""
    for e in _plan().text_entries(json_grammar=True):
        assert "max_tokens" not in _kw(e)


# ---- provider payload construction ----


class _FakeResp:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"choices": [{"message": {"content": "{}"}}]}


class _FakeClient:
    def __init__(self):
        self.payloads: list[dict] = []

    async def post(self, url, json=None, headers=None):
        self.payloads.append(json)
        return _FakeResp()


async def test_groq_text_payload_includes_max_tokens(monkeypatch):
    from app.services.ai.providers import groq

    client = _FakeClient()
    monkeypatch.setattr(groq, "get_cloud_client", AsyncMock(return_value=client))
    monkeypatch.setattr(groq, "resolve_provider_api_key", AsyncMock(return_value="k"))
    await groq.call_groq_text("prompt", max_tokens=512)
    assert client.payloads[0]["max_tokens"] == 512


async def test_groq_text_payload_omits_max_tokens_when_none(monkeypatch):
    from app.services.ai.providers import groq

    client = _FakeClient()
    monkeypatch.setattr(groq, "get_cloud_client", AsyncMock(return_value=client))
    monkeypatch.setattr(groq, "resolve_provider_api_key", AsyncMock(return_value="k"))
    await groq.call_groq_text("prompt")
    assert "max_tokens" not in client.payloads[0]


async def test_openai_vision_payload_includes_max_tokens(monkeypatch):
    from app.services.ai.providers import openai

    client = _FakeClient()
    monkeypatch.setattr(openai, "get_cloud_client", AsyncMock(return_value=client))
    monkeypatch.setattr(openai, "resolve_provider_api_key", AsyncMock(return_value="k"))
    await openai.call_openai_vision("b64", "image/jpeg", "prompt", max_tokens=768)
    assert client.payloads[0]["max_tokens"] == 768


async def test_gemini_generation_config_includes_max_output_tokens(monkeypatch):
    from app.services.ai.providers import gemini

    client = _FakeClient()

    class _GeminiResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}

    class _GeminiClient:
        async def post(self, url, json=None, headers=None):
            client.payloads.append(json)
            return _GeminiResp()

    monkeypatch.setattr(gemini, "_adc_access_token", lambda: None)
    monkeypatch.setattr(gemini, "resolve_provider_api_key", AsyncMock(return_value="k"))
    monkeypatch.setattr(gemini, "get_cloud_client", AsyncMock(return_value=_GeminiClient()))
    await gemini.call_gemini_text("prompt", max_tokens=512)
    assert client.payloads[0]["generationConfig"]["maxOutputTokens"] == 512


# ---- integration: call_text_extraction threads max_tokens from settings ----


async def test_call_text_extraction_threads_max_tokens_to_cloud():
    captured: dict = {}

    async def groq(prompt, **kw):
        captured["groq"] = kw
        return JSON_OK

    with (
        patch.object(dex, "call_groq_text", groq),
        patch.object(dex, "call_openrouter_text", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_text", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_text", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_text", AsyncMock(return_value=None)),
    ):
        await dex.call_text_extraction("some document text", [""], _plan())

    assert captured["groq"].get("max_tokens") == dex.settings.EXTRACTION_MAX_TOKENS


async def test_format_ocr_transcription_not_capped():
    """The cosmetic transcription-format call is left uncapped (may run long)."""
    captured: dict = {}

    async def groq(prompt, **kw):
        captured["groq"] = kw
        return "formatted"

    with (
        patch.object(dex, "call_groq_text", groq),
        patch.object(dex, "call_openrouter_text", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_text", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_text", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_text", AsyncMock(return_value=None)),
    ):
        await dex._format_ocr_transcription("raw OCR text long enough to format", [""], _plan())

    assert "max_tokens" not in captured["groq"]
