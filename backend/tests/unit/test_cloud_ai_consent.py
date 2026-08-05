"""Per-member cloud-AI consent: opted-out members never egress to a cloud provider.

The AIService builds its cloud-provider chain from the household config in three
places; ``set_cloud_consent(False)`` empties that chain so only local Ollama is
used. These tests pin that behaviour against the non-streaming ``_call_ai`` path
(the streaming insight/chat paths use the identical guard).
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.base import FamilyMember
from app.services.ai_service import AIService


@pytest.fixture
def mock_db():
    from unittest.mock import AsyncMock

    db = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def ai_service(mock_db):
    return AIService(mock_db)


@pytest.mark.asyncio
async def test_set_cloud_consent_returns_self_and_sets_flag(ai_service):
    """Consent defaults True; setter flips it and returns the service for chaining."""
    assert ai_service.cloud_ai_consent is True
    returned = ai_service.set_cloud_consent(False)
    assert returned is ai_service
    assert ai_service.cloud_ai_consent is False


@pytest.mark.asyncio
async def test_call_ai_skips_cloud_when_consent_disabled(ai_service):
    """Opted-out member: cloud providers are never called; only Ollama is tried."""
    from app.schemas.ai_provider_config import default_provider_config

    ai_service.set_cloud_consent(False)
    mock_ollama = AsyncMock(return_value="local-only response")
    mock_groq = AsyncMock(return_value="SHOULD NOT BE USED")
    mock_gemini = AsyncMock(return_value="SHOULD NOT BE USED")
    mock_openrouter = AsyncMock(return_value="SHOULD NOT BE USED")
    mock_openai = AsyncMock(return_value="SHOULD NOT BE USED")
    with (
        patch.object(
            ai_service,
            "_get_provider_config",
            new_callable=AsyncMock,
            return_value=default_provider_config(),
        ),
        patch.object(ai_service, "_call_ollama_text", mock_ollama),
        patch.object(ai_service, "_call_groq_text", mock_groq),
        patch.object(ai_service, "_call_gemini_text", mock_gemini),
        patch.object(ai_service, "_call_openrouter_text", mock_openrouter),
        patch.object(ai_service, "_call_openai_text", mock_openai),
    ):
        result, provider = await ai_service._call_ai("prompt", "")
    assert result == "local-only response"
    assert "Ollama" in provider
    mock_ollama.assert_called_once()
    mock_groq.assert_not_called()
    mock_gemini.assert_not_called()
    mock_openrouter.assert_not_called()
    mock_openai.assert_not_called()


def test_member_model_defaults_to_consent_true():
    """The cloud_ai_consent column is non-nullable and defaults True (legacy)."""
    col = FamilyMember.__table__.c.cloud_ai_consent
    assert col.nullable is False
    assert col.default.arg is True


# ── Extraction plan: consent restricts the provider chain to local ──────────


def test_extraction_plan_local_only_drops_cloud():
    """local_only() keeps Ollama and drops every cloud provider entry."""
    from app.services.ai.document_extractor import ExtractionProviderPlan, _PlanItem

    plan = ExtractionProviderPlan(
        items=[
            _PlanItem(provider_id="groq", model="llama", is_local=False),
            _PlanItem(provider_id="gemini", model="flash", is_local=False),
            _PlanItem(provider_id="ollama", model="qwen3", is_local=True),
        ]
    )
    local = plan.local_only()
    assert [it.provider_id for it in local.items] == ["ollama"]
    assert all(it.is_local for it in local.items)


def test_extraction_plan_local_only_preserves_already_local_plan():
    """When the plan is already local-only, local_only() returns the same object."""
    from app.services.ai.document_extractor import ExtractionProviderPlan, _PlanItem

    plan = ExtractionProviderPlan(
        items=[_PlanItem(provider_id="ollama", model="qwen3", is_local=True)]
    )
    assert plan.local_only() is plan

