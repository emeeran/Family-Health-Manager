"""Unit tests for AI drug interaction checking — response parsing logic."""
import json
import pytest
from unittest.mock import AsyncMock

from app.services.ai_service import AIService


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def ai_service(mock_db):
    return AIService(mock_db)


def _medications(n=3):
    """Generate n test medication dicts."""
    base = [
        {"medicine": "Warfarin 5mg", "type": "Tab", "dosage": "0-0-1"},
        {"medicine": "Aspirin 75mg", "type": "Tab", "dosage": "0-1-0"},
        {"medicine": "Omeprazole 20mg", "type": "Cap", "dosage": "1-0-0"},
        {"medicine": "Metformin 500mg", "type": "Tab", "dosage": "1-0-1"},
        {"medicine": "Amlodipine 5mg", "type": "Tab", "dosage": "0-1-0"},
    ]
    return base[:n]


@pytest.mark.asyncio
async def test_check_interactions_returns_empty_for_lt2(ai_service):
    """< 2 medications → immediately returns empty list, no AI call."""
    result = await ai_service.check_drug_interactions(_medications(1))
    assert result == []

    result = await ai_service.check_drug_interactions([])
    assert result == []


@pytest.mark.asyncio
async def test_check_interactions_parses_valid_json(ai_service):
    """AI returns clean JSON array → parsed correctly."""
    interaction = [
        {
            "drugs": ["Warfarin", "Aspirin"],
            "severity": "high",
            "description": "Increased bleeding risk",
            "recommendation": "Monitor INR closely",
        }
    ]
    ai_service._call_ai = AsyncMock(return_value=(json.dumps(interaction), "test-provider"))

    result = await ai_service.check_drug_interactions(_medications(3))

    assert len(result) == 1
    assert result[0]["drugs"] == ["Warfarin", "Aspirin"]
    assert result[0]["severity"] == "high"


@pytest.mark.asyncio
async def test_check_interactions_parses_markdown_fenced_json(ai_service):
    """AI wraps response in ```json ... ``` fences → still parsed."""
    interaction = [
        {
            "drugs": ["Warfarin", "Aspirin"],
            "severity": "high",
            "description": "Bleeding risk",
            "recommendation": "Monitor INR",
        }
    ]
    raw = f"```json\n{json.dumps(interaction)}\n```"
    ai_service._call_ai = AsyncMock(return_value=(raw, "test-provider"))

    result = await ai_service.check_drug_interactions(_medications(2))

    assert len(result) == 1
    assert result[0]["severity"] == "high"


@pytest.mark.asyncio
async def test_check_interactions_parses_json_with_surrounding_text(ai_service):
    """AI returns text before/after the JSON array → bracket-matching extracts it."""
    interaction = [
        {
            "drugs": ["A", "B"],
            "severity": "low",
            "description": "Minor interaction",
            "recommendation": "No action needed",
        }
    ]
    raw = f"Here is the analysis:\n{json.dumps(interaction)}\nHope this helps!"
    ai_service._call_ai = AsyncMock(return_value=(raw, "test-provider"))

    result = await ai_service.check_drug_interactions(_medications(2))

    assert len(result) == 1


@pytest.mark.asyncio
async def test_check_interactions_empty_array(ai_service):
    """AI returns [] → no interactions."""
    ai_service._call_ai = AsyncMock(return_value=("[]", "test-provider"))

    result = await ai_service.check_drug_interactions(_medications(2))
    assert result == []


@pytest.mark.asyncio
async def test_check_interactions_multiple_interactions(ai_service):
    """AI returns multiple interactions → all parsed."""
    interactions = [
        {
            "drugs": ["Warfarin", "Aspirin"],
            "severity": "high",
            "description": "Bleeding risk",
            "recommendation": "Monitor INR",
        },
        {
            "drugs": ["Omeprazole", "Warfarin"],
            "severity": "moderate",
            "description": "May increase warfarin levels",
            "recommendation": "Check INR more frequently",
        },
        {
            "drugs": ["Amlodipine", "Metformin"],
            "severity": "low",
            "description": "Minor interaction",
            "recommendation": "Monitor blood pressure",
        },
    ]
    ai_service._call_ai = AsyncMock(return_value=(json.dumps(interactions), "test-provider"))

    result = await ai_service.check_drug_interactions(_medications(5))

    assert len(result) == 3
    severities = {r["severity"] for r in result}
    assert severities == {"high", "moderate", "low"}


@pytest.mark.asyncio
async def test_check_interactions_malformed_json_returns_empty(ai_service):
    """AI returns garbage → returns empty list, doesn't crash."""
    ai_service._call_ai = AsyncMock(return_value=("I cannot analyze this.", "test-provider"))

    result = await ai_service.check_drug_interactions(_medications(2))
    assert result == []


@pytest.mark.asyncio
async def test_check_interactions_partial_json_returns_empty(ai_service):
    """AI returns truncated JSON → returns empty list."""
    ai_service._call_ai = AsyncMock(return_value=('[{"drugs": ["A", "B"], "severity":', "test-provider"))

    result = await ai_service.check_drug_interactions(_medications(2))
    assert result == []


@pytest.mark.asyncio
async def test_check_interactions_empty_ai_response(ai_service):
    """AI returns empty string → returns empty list."""
    ai_service._call_ai = AsyncMock(return_value=("", "test-provider"))

    result = await ai_service.check_drug_interactions(_medications(2))
    assert result == []


@pytest.mark.asyncio
async def test_check_interactions_none_ai_response(ai_service):
    """AI returns None → returns empty list."""
    ai_service._call_ai = AsyncMock(return_value=(None, "test-provider"))

    result = await ai_service.check_drug_interactions(_medications(2))
    assert result == []


@pytest.mark.asyncio
async def test_check_interactions_nested_json_array(ai_service):
    """Response with nested arrays inside the main array still bracket-matches."""
    interactions = [
        {
            "drugs": ["Drug A", "Drug B"],
            "severity": "high",
            "description": "Risk [important] interaction",
            "recommendation": "See doctor",
        }
    ]
    raw = json.dumps(interactions)
    ai_service._call_ai = AsyncMock(return_value=(raw, "test-provider"))

    result = await ai_service.check_drug_interactions(_medications(2))
    assert len(result) == 1


# ── _strip_markdown_fences static method tests ───────────────────────


def test_strip_markdown_fences_json():
    raw = "```json\n[{\"drugs\": [\"A\"]}]\n```"
    cleaned = AIService._strip_markdown_fences(raw)
    assert cleaned.startswith("[")
    assert cleaned.endswith("]")


def test_strip_markdown_fences_plain():
    raw = "```\n[\"hello\"]\n```"
    cleaned = AIService._strip_markdown_fences(raw)
    assert "```" not in cleaned


def test_strip_markdown_fences_no_fences():
    raw = '[{"drugs": ["A"]}]'
    cleaned = AIService._strip_markdown_fences(raw)
    assert cleaned == raw
