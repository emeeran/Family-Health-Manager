"""Unit tests for AI service."""

import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from app.services.ai_service import AIService
from app.models.base import Message, MessageRole, Conversation


@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    """Reset circuit breaker and AI response cache state between tests to prevent leakage."""
    from app.services.ai.base import _circuit_state, _ai_response_cache

    _circuit_state.clear()
    _ai_response_cache.clear()
    yield
    _circuit_state.clear()
    _ai_response_cache.clear()


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def ai_service(mock_db):
    """Create AIService instance."""
    return AIService(mock_db)


@pytest.mark.asyncio
async def test_generate_insight(ai_service, mock_db):
    """Test generating AI insight."""
    prompt = "Explain this lab result"

    with (
        patch.object(ai_service, "_call_ollama_insight") as mock_call,
        patch("app.services.ai_service.settings") as mock_settings,
    ):
        mock_call.return_value = ("AI response", "test-provider")
        mock_settings.AI_VERIFICATION_ENABLED = False

        insight = await ai_service.generate_insight(prompt=prompt)

        assert insight.prompt == prompt
        assert insight.response == "AI response"
        assert insight.provider_used == "test-provider"


@pytest.mark.asyncio
async def test_generate_insight_with_member_context(ai_service, mock_db):
    """Test generating insight with member context."""
    member_id = uuid4()
    prompt = "What's my health status?"

    mock_member = MagicMock()
    mock_member.first_name = "John"
    mock_member.last_name = "Doe"
    mock_member.date_of_birth = date(1990, 1, 1)
    mock_member.medical_history_summary = "Diabetes"
    mock_member.gender = MagicMock(value="male")
    mock_member.blood_group = None
    mock_member.height_cm = None
    mock_member.weight_kg = None
    mock_member.allergies_json = None
    mock_member.family_history = None

    get_result = MagicMock()
    get_result.scalar_one.return_value = mock_member
    mock_db.execute = AsyncMock(return_value=get_result)

    with (
        patch.object(ai_service, "_build_member_context", return_value="Patient context"),
        patch.object(ai_service, "_call_ollama_insight") as mock_call,
        patch("app.services.ai_service.settings") as mock_settings,
    ):
        mock_call.return_value = ("AI response", "test-provider")
        mock_settings.AI_VERIFICATION_ENABLED = False

        insight = await ai_service.generate_insight(prompt=prompt, member_id=member_id)

        assert insight is not None


@pytest.mark.asyncio
async def test_call_ai_failover(ai_service):
    """Test AI provider failover chain — all providers fail with no keys."""
    from app.schemas.ai_provider_config import default_provider_config

    mock_ollama = AsyncMock(return_value=None)
    mock_openrouter = AsyncMock(return_value=None)
    mock_groq = AsyncMock(return_value=None)
    mock_gemini = AsyncMock(return_value=None)
    mock_openai = AsyncMock(return_value=None)
    with (
        patch.object(
            ai_service,
            "_get_provider_config",
            new_callable=AsyncMock,
            return_value=default_provider_config(),
        ),
        patch.object(ai_service, "_call_ollama_text", mock_ollama),
        patch.object(ai_service, "_call_openrouter_text", mock_openrouter),
        patch.object(ai_service, "_call_groq_text", mock_groq),
        patch.object(ai_service, "_call_gemini_text", mock_gemini),
        patch.object(ai_service, "_call_openai_text", mock_openai),
    ):
        with pytest.raises(ValueError, match="All AI providers failed"):
            await ai_service._call_ai("Test prompt", "")


@pytest.mark.asyncio
async def test_call_ai_ollama_first_then_cloud(ai_service):
    """Test Ollama is tried first, then cloud providers as fallback."""
    from app.schemas.ai_provider_config import default_provider_config

    mock_groq = AsyncMock(return_value=None)
    mock_gemini = AsyncMock(return_value="Gemini response")
    mock_ollama = AsyncMock(return_value=None)
    mock_openrouter = AsyncMock(return_value=None)
    mock_openai = AsyncMock(return_value=None)
    with (
        patch.object(
            ai_service,
            "_get_provider_config",
            new_callable=AsyncMock,
            return_value=default_provider_config(),
        ),
        patch.object(ai_service, "_call_groq_text", mock_groq),
        patch.object(ai_service, "_call_gemini_text", mock_gemini),
        patch.object(ai_service, "_call_ollama_text", mock_ollama),
        patch.object(ai_service, "_call_openrouter_text", mock_openrouter),
        patch.object(ai_service, "_call_openai_text", mock_openai),
    ):
        result, provider = await ai_service._call_ai("Test prompt", "")
        assert result == "Gemini response"
        assert "Gemini" in provider
        # Ollama tried first, then cloud fallback
        mock_ollama.assert_called_once()
        mock_groq.assert_called_once()
        mock_gemini.assert_called_once()


@pytest.mark.asyncio
async def test_call_ai_fallback_through_default_chain(ai_service):
    """Default chain fallback: Ollama + Groq fail -> Gemini wins.

    The default chain is now [groq, gemini, ollama] (OpenRouter/OpenAI are
    opt-in). This proves _call_ai iterates past provider failures to a winner.
    """
    from app.schemas.ai_provider_config import default_provider_config

    mock_groq = AsyncMock(return_value=None)
    mock_gemini = AsyncMock(return_value="Gemini response")
    mock_ollama = AsyncMock(return_value=None)
    with (
        patch.object(
            ai_service,
            "_get_provider_config",
            new_callable=AsyncMock,
            return_value=default_provider_config(),
        ),
        patch.object(ai_service, "_call_groq_text", mock_groq),
        patch.object(ai_service, "_call_gemini_text", mock_gemini),
        patch.object(ai_service, "_call_ollama_text", mock_ollama),
    ):
        result, provider = await ai_service._call_ai("Test prompt", "")
        assert result == "Gemini response"
        assert "Gemini" in provider


@pytest.mark.asyncio
async def test_chat(ai_service, mock_db):
    """Test sending message in conversation."""
    conversation_id = uuid4()

    mock_conversation = Conversation(
        id=conversation_id,
        household_id=uuid4(),
        family_member_id=None,
    )

    get_result = MagicMock()
    get_result.scalar_one.return_value = mock_conversation
    mock_db.execute = AsyncMock(return_value=get_result)

    with patch.object(ai_service, "_call_ai") as mock_call:
        mock_call.return_value = ("AI response", "test-provider")

        with patch.object(ai_service, "_get_conversation_history", return_value=""):
            user_msg, assistant_msg, provider, health_context = await ai_service.chat(
                conversation_id=conversation_id,
                user_message="Hello",
            )

            assert user_msg.role == MessageRole.USER
            assert assistant_msg.role == MessageRole.ASSISTANT


@pytest.mark.asyncio
async def test_get_conversation_history(ai_service, mock_db):
    """Test getting conversation history."""
    conversation_id = uuid4()
    mock_message = Message(
        id=uuid4(),
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content="Hello",
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_message]
    mock_db.execute = AsyncMock(return_value=mock_result)

    history = await ai_service._get_conversation_history(conversation_id)

    assert "User: Hello" in history


# ── Transcription report generation ──


def _report_extracted_data() -> dict:
    return {
        "record_type": "doctor_visit",
        "record_date": "2024-01-15",
        "chief_complaint": "Lower abdominal pain",
        "diagnosis": "Pelvic Inflammatory Disease",
        "prescriptions": [
            {
                "type": "Tab",
                "medicine": "Doxycycline",
                "dosage": "100mg",
                "timing": "BD",
                "duration": "10 days",
            }
        ],
        "lab_tests": [
            {"test_name": "Haemoglobin", "result": "8.6", "units": "gm%", "ref_value": "12.0-15.5"}
        ],
    }


def _report_member_ctx() -> dict:
    return {
        "name": "Mrs. Jenitha",
        "patient_id": "KF2446",
        "age_gender": "41 Years / Female",
        "phone": "7598287415",
        "address": "Chennai, Tamil Nadu, India",
    }


def _report_provider_ctx() -> dict:
    return {"name": "Dr. Sangeetha S", "speciality": "Obstetrician & Gynaecologist"}


@pytest.mark.asyncio
async def test_generate_transcription_report_uses_ai(ai_service):
    """When the AI provider responds, its output is returned (fences stripped)."""
    ai_report = "## Medical Records Transcription Report\n\nAI-generated body."
    with patch.object(
        ai_service, "_call_ai", new_callable=AsyncMock, return_value=(ai_report, "mock-provider")
    ):
        result = await ai_service.generate_transcription_report(
            _report_extracted_data(), _report_member_ctx(), _report_provider_ctx()
        )
    assert "Medical Records Transcription Report" in result
    assert "AI-generated body." in result


@pytest.mark.asyncio
async def test_generate_transcription_report_falls_back_to_template(ai_service):
    """When every AI provider fails, the deterministic template is used."""
    with patch.object(
        ai_service,
        "_call_ai",
        new_callable=AsyncMock,
        side_effect=RuntimeError("all providers down"),
    ):
        result = await ai_service.generate_transcription_report(
            _report_extracted_data(), _report_member_ctx(), _report_provider_ctx()
        )
    # Institution header is the provider name.
    assert result.startswith("# Dr. Sangeetha S")
    assert "Medical Records Transcription Report" in result
    assert "Mrs. Jenitha" in result
    assert "KF2446" in result
    # Medications + lab tables are populated from structured data.
    assert "Doxycycline" in result
    assert "Haemoglobin" in result


def test_build_template_transcription_report_omits_empty_sections():
    """A pure lab report (no prescriptions) omits the Treatment Plan section."""
    extracted = {
        "record_type": "lab_report",
        "record_date": "2024-02-01",
        "lab_tests": [{"test_name": "HbA1c", "result": "8.9", "ref_value": "< 6.0%"}],
    }
    member_ctx = {"name": "Mr. Test", "age_gender": "50 Years / Male"}
    report = AIService._build_template_transcription_report(extracted, member_ctx, {})

    assert "1. PATIENT IDENTIFICATION & DEMOGRAPHICS" in report
    assert "4. DIAGNOSTIC SUMMARY" in report
    assert "HbA1c" in report
    # No prescriptions → section 3 (Treatment Plan) must be absent.
    assert "3. TREATMENT PLAN & MEDICAL ORDERS" not in report
