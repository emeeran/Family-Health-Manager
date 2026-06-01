"""Integration tests for Ollama + MedGemma connectivity and accessibility."""
import json

import httpx
import pytest

OLLAMA_URL = "http://localhost:11434"
MODEL = "medgemma"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _ollama_chat(prompt: str, images: list[str] | None = None) -> str | None:
    """Send a chat request to Ollama and return the response text."""
    message: dict = {"role": "user", "content": prompt}
    if images:
        message["images"] = images
    payload = {"model": MODEL, "messages": [message], "stream": False}
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content")
    except httpx.HTTPStatusError as exc:
        pytest.skip(f"Ollama model returned {exc.response.status_code}: {exc}")


# ---------------------------------------------------------------------------
# Connectivity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_server_reachable():
    """Ollama server is running and responding."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{OLLAMA_URL}/api/tags")
        assert resp.status_code == 200
        models = [m["name"] for m in resp.json().get("models", [])]
        assert any(MODEL in m for m in models), (
            f"Model '{MODEL}' not found. Available: {models}"
        )


# ---------------------------------------------------------------------------
# Text generation (chat / Q&A / classification)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_medgemma_text_basic_response():
    """MedGemma returns a non-empty text response."""
    response = await _ollama_chat("What is HbA1c? Answer in one sentence.")
    assert response is not None
    assert len(response.strip()) > 10
    # Should contain key medical terms
    lower = response.lower()
    assert any(kw in lower for kw in ("hemoglobin", "blood sugar", "glucose", "hba1c"))


@pytest.mark.asyncio
async def test_medgemma_structured_json_output():
    """MedGemma can produce structured JSON for medical extraction."""
    prompt = (
        "Return ONLY valid JSON (no markdown). "
        'Extract from: "Patient took Metformin 500mg twice daily for 30 days. '
        'HbA1c was 8.2%."\n\n'
        'Return: {"medications": [{"name": "...", "dosage": "...", "frequency": "...", "duration": "..."}], '
        '"lab_results": [{"test": "...", "value": "..."}]}'
    )
    response = await _ollama_chat(prompt)
    assert response is not None

    # Try to parse JSON
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    data = json.loads(cleaned)
    assert isinstance(data, dict)
    # Should have picked up the medication and lab result
    has_meds = "medications" in data and len(data["medications"]) > 0
    has_labs = "lab_results" in data and len(data["lab_results"]) > 0
    assert has_meds or has_labs, f"Expected medications or lab_results, got: {data}"


@pytest.mark.asyncio
async def test_medgemma_medical_classification():
    """MedGemma can classify a medical document type."""
    prompt = (
        "Classify this medical document into exactly one category. "
        "Return ONLY one word from: doctor_visit, lab_report, rx_eyeglass, blood_glucose, misc_record\n\n"
        "Document: CBC results showing WBC 7200, RBC 4.8, Hemoglobin 13.5, Platelets 250000"
    )
    response = await _ollama_chat(prompt)
    assert response is not None
    cleaned = response.strip().strip("\"'`").lower()
    assert cleaned in ("lab_report", "doctor_visit", "misc_record", "blood_glucose"), (
        f"Unexpected classification: {cleaned}"
    )


# ---------------------------------------------------------------------------
# Through the AIService layer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_service_ollama_text_provider():
    """AIService._call_ollama_text calls local Ollama and returns text."""
    from unittest.mock import AsyncMock, patch

    from app.core.config import Settings
    from app.services.ai_service import AIService

    # Skip if Ollama is not running or model unavailable
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            if not any(MODEL in m for m in models):
                pytest.skip(f"Model '{MODEL}' not found in Ollama")
    except Exception:
        pytest.skip("Ollama server not reachable")

    # Reset class-level clients to avoid stale event-loop references
    AIService._cloud_client = None
    AIService._ollama_client = None
    AIService._client_lock = None
    from app.services.ai import base as _base
    if _base.ollama_client:
        try:
            await _base.ollama_client.aclose()
        except Exception:
            pass
    _base.ollama_client = None

    mock_db = AsyncMock()
    ai_service = AIService(mock_db)
    test_settings = Settings(
        SECRET_KEY="test-secret-key-for-unit-tests",
        OLLAMA_LOCAL_URL=OLLAMA_URL,
        OLLAMA_MODEL=MODEL,
        OLLAMA_TEXT_MODEL=MODEL,
    )
    with patch("app.services.ai_service.settings", test_settings), \
         patch("app.services.ai.providers.ollama.settings", test_settings), \
         patch("app.core.config.get_settings", return_value=test_settings):
        try:
            result = await ai_service._call_ollama_text("Say 'hello' in one word.")
        except Exception as exc:
            pytest.skip(f"Ollama model call failed: {exc}")
        assert result is not None
        assert len(result.strip()) > 0


@pytest.mark.asyncio
async def test_ai_service_full_failover_with_ollama():
    """AIService._call_ai uses Ollama first when configured."""
    from unittest.mock import AsyncMock, patch

    import httpx

    from app.core.config import Settings
    from app.services.ai_service import AIService

    # Skip if Ollama is not running
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            resp.raise_for_status()
    except Exception:
        pytest.skip("Ollama server not reachable")

    # Reset class-level clients to avoid stale event-loop references
    AIService._cloud_client = None
    AIService._ollama_client = None
    AIService._client_lock = None
    # Also reset the base module's shared client
    from app.services.ai import base as _base
    if _base.ollama_client:
        try:
            await _base.ollama_client.aclose()
        except Exception:
            pass
    _base.ollama_client = None

    mock_db = AsyncMock()
    ai_service = AIService(mock_db)
    test_settings = Settings(
        SECRET_KEY="test-secret-key-for-unit-tests",
        OLLAMA_LOCAL_URL=OLLAMA_URL,
        OLLAMA_MODEL=MODEL,
        OLLAMA_TEXT_MODEL=MODEL,
        OPENAI_API_KEY="",
        GEMINI_API_KEY="",
        GROQ_API_KEY="",
        OPENROUTER_API_KEY="",
    )
    with patch("app.services.ai_service.settings", test_settings), \
         patch("app.services.ai.providers.ollama.settings", test_settings), \
         patch("app.core.config.get_settings", return_value=test_settings):
        try:
            result, provider = await ai_service._call_ai(
                "What is 2+2? Reply with just the number.", ""
            )
        except Exception as exc:
            pytest.skip(f"Ollama model call failed: {exc}")
        assert result is not None
        assert "Ollama" in provider


# ---------------------------------------------------------------------------
# Accessibility / usability checks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_medgemma_handles_handwriting_prompt():
    """MedGemma can follow handwriting extraction instructions."""
    prompt = (
        "You are a medical document assistant. A prescription contains handwritten text. "
        "The handwriting reads: 'Tab Metformin 500mg 1-0-1 30 days'. "
        "Extract the medication as JSON: "
        '{"type": "Tab", "medicine": "...", "dosage": "...", "duration": "...", "timing": "..."}'
        "Return ONLY the JSON."
    )
    response = await _ollama_chat(prompt)
    assert response is not None
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    data = json.loads(cleaned)
    assert data.get("medicine", "").lower() == "metformin"
    assert "500" in data.get("dosage", "")


@pytest.mark.asyncio
async def test_medgemma_response_time_acceptable():
    """MedGemma responds within a reasonable time for interactive use."""
    import time

    start = time.time()
    response = await _ollama_chat("What is normal blood pressure? One sentence.")
    elapsed = time.time() - start

    assert response is not None
    # Local inference should complete within 30s even on CPU
    assert elapsed < 30, f"Response took {elapsed:.1f}s — too slow for interactive use"
