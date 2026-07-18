"""Unit tests for the sequential extraction provider chain.

Exercises ``call_text_extraction`` → ``_run_provider_chain``: providers are
tried in priority order (Groq → OpenRouter → Gemini → OpenAI → Ollama), the
first non-empty result wins, exceptions/timeouts fall through to the next, and
the local Ollama entry is exempt from the short failover timeout. All provider
functions are mocked — no network.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import app.services.ai.document_extractor as dex

JSON_OK = '{"record_type": "lab_report"}'


async def test_first_provider_success_skips_the_rest():
    groq = AsyncMock(return_value=JSON_OK)
    openrouter = AsyncMock(return_value="should not be reached")
    with (
        patch.object(dex, "call_groq_text", groq),
        patch.object(dex, "call_openrouter_text", openrouter),
        patch.object(dex, "call_gemini_text", AsyncMock()),
        patch.object(dex, "call_openai_text", AsyncMock()),
        patch.object(dex, "call_ollama_text", AsyncMock()),
    ):
        ref = [""]
        out = await dex.call_text_extraction("pdf text", ref)
    assert out == JSON_OK
    assert ref[0] == "Groq text"
    openrouter.assert_not_called()  # Groq won → later providers never tried


async def test_fall_through_on_exception_to_next_provider():
    gemini = AsyncMock(return_value=JSON_OK)
    with (
        patch.object(dex, "call_groq_text", AsyncMock(side_effect=RuntimeError("401"))),
        patch.object(dex, "call_openrouter_text", AsyncMock(side_effect=RuntimeError("402"))),
        patch.object(dex, "call_gemini_text", gemini),
        patch.object(dex, "call_openai_text", AsyncMock()),
        patch.object(dex, "call_ollama_text", AsyncMock()),
    ):
        ref = [""]
        out = await dex.call_text_extraction("pdf text", ref)
    assert out == JSON_OK
    assert ref[0] == "Gemini text"  # Groq + OpenRouter failed → Gemini won


async def test_cloud_timeout_falls_through(monkeypatch):
    monkeypatch.setattr(dex.settings, "EXTRACTION_PROVIDER_TIMEOUT", 0.1)

    async def slow(*_a, **_kw):
        await asyncio.sleep(5)
        return "late"

    openrouter = AsyncMock(return_value=JSON_OK)
    with (
        patch.object(dex, "call_groq_text", AsyncMock(side_effect=slow)),
        patch.object(dex, "call_openrouter_text", openrouter),
        patch.object(dex, "call_gemini_text", AsyncMock()),
        patch.object(dex, "call_openai_text", AsyncMock()),
        patch.object(dex, "call_ollama_text", AsyncMock()),
    ):
        ref = [""]
        out = await dex.call_text_extraction("pdf text", ref)
    assert out == JSON_OK
    assert ref[0] == "OpenRouter text"  # Groq exceeded the cap → OpenRouter tried


async def test_ollama_not_killed_by_short_cloud_timeout(monkeypatch):
    # Ollama is the local fallback: it must outlast the short cloud cap.
    monkeypatch.setattr(dex.settings, "EXTRACTION_PROVIDER_TIMEOUT", 0.1)

    async def slow_but_ok(*_a, **_kw):
        await asyncio.sleep(0.3)  # longer than the 0.1s cloud cap
        return JSON_OK

    with (
        patch.object(dex, "call_groq_text", AsyncMock(side_effect=RuntimeError)),
        patch.object(dex, "call_openrouter_text", AsyncMock(side_effect=RuntimeError)),
        patch.object(dex, "call_gemini_text", AsyncMock(side_effect=RuntimeError)),
        patch.object(dex, "call_openai_text", AsyncMock(side_effect=RuntimeError)),
        patch.object(dex, "call_ollama_text", slow_but_ok),
    ):
        ref = [""]
        out = await dex.call_text_extraction("pdf text", ref)
    assert out == JSON_OK
    assert ref[0] == "Ollama text"


async def test_all_providers_fail_returns_none():
    with (
        patch.object(dex, "call_groq_text", AsyncMock(side_effect=RuntimeError)),
        patch.object(dex, "call_openrouter_text", AsyncMock(side_effect=RuntimeError)),
        patch.object(dex, "call_gemini_text", AsyncMock(side_effect=RuntimeError)),
        patch.object(dex, "call_openai_text", AsyncMock(side_effect=RuntimeError)),
        patch.object(dex, "call_ollama_text", AsyncMock(return_value=None)),
    ):
        out = await dex.call_text_extraction("pdf text", [""])
    assert out is None
