"""Unit tests for AI service."""
import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from app.services.ai_service import AIService
from app.models.base import Message, MessageRole, Conversation


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

    with patch.object(ai_service, "_call_ollama_insight") as mock_call, \
         patch("app.services.ai_service.settings") as mock_settings:
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

    with patch.object(ai_service, "_build_member_context", return_value="Patient context"), \
         patch.object(ai_service, "_call_ollama_insight") as mock_call, \
         patch("app.services.ai_service.settings") as mock_settings:
        mock_call.return_value = ("AI response", "test-provider")
        mock_settings.AI_VERIFICATION_ENABLED = False

        insight = await ai_service.generate_insight(prompt=prompt, member_id=member_id)

        assert insight is not None


@pytest.mark.asyncio
async def test_call_ai_failover(ai_service):
    """Test AI provider failover chain — all providers fail with no keys."""
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.OLLAMA_LOCAL_URL = ""
        mock_settings.OLLAMA_MODEL = "medgemma"
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.GEMINI_API_KEY = ""
        mock_settings.GROQ_API_KEY = ""
        mock_settings.OPENROUTER_API_KEY = ""
        with pytest.raises(ValueError, match="All AI providers failed"):
            await ai_service._call_ai("Test prompt", "")


@pytest.mark.asyncio
async def test_call_ai_groq_first_then_gemini(ai_service):
    """Test Groq is tried first (fastest), then Gemini in the provider chain."""
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.OLLAMA_LOCAL_URL = "http://localhost:11434"
        mock_settings.OLLAMA_MODEL = "medgemma"
        mock_settings.OLLAMA_TEXT_MODEL = "llama3.2:3b"
        mock_settings.OLLAMA_TIMEOUT = 90
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.GEMINI_API_KEY = ""
        mock_settings.GROQ_API_KEY = ""
        mock_settings.OPENROUTER_API_KEY = ""
        mock_groq = AsyncMock(return_value=None)
        mock_gemini = AsyncMock(return_value="Gemini response")
        mock_ollama = AsyncMock(return_value=None)
        with patch.object(ai_service, "_call_groq_text", mock_groq), \
             patch.object(ai_service, "_call_gemini_text", mock_gemini), \
             patch.object(ai_service, "_call_ollama_text", mock_ollama):
            result, provider = await ai_service._call_ai("Test prompt", "")
            assert result == "Gemini response"
            assert provider == "Google Gemini 2.5 Flash"
            mock_groq.assert_called_once()
            mock_gemini.assert_called_once()


@pytest.mark.asyncio
async def test_call_ai_fallback_to_openrouter(ai_service):
    """Test fallback to OpenRouter when Groq, Gemini, and Ollama fail."""
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.OLLAMA_LOCAL_URL = "http://localhost:11434"
        mock_settings.OLLAMA_MODEL = "medgemma"
        mock_settings.OLLAMA_TEXT_MODEL = "llama3.2:3b"
        mock_settings.OLLAMA_TIMEOUT = 90
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.GEMINI_API_KEY = ""
        mock_settings.GROQ_API_KEY = ""
        mock_settings.OPENROUTER_API_KEY = "test-key"
        mock_groq = AsyncMock(return_value=None)
        mock_gemini = AsyncMock(return_value=None)
        mock_ollama = AsyncMock(return_value=None)
        mock_openrouter = AsyncMock(return_value="OpenRouter response")
        with patch.object(ai_service, "_call_groq_text", mock_groq), \
             patch.object(ai_service, "_call_gemini_text", mock_gemini), \
             patch.object(ai_service, "_call_ollama_text", mock_ollama), \
             patch.object(ai_service, "_call_openrouter_text", mock_openrouter):
            result, provider = await ai_service._call_ai("Test prompt", "")
            assert result == "OpenRouter response"
            assert provider == "OpenRouter DeepSeek V4 Flash"


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
