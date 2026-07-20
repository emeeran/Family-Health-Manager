"""Tests for the Concise (brief) vs Comprehensive report generation mode."""

import pytest

from app.prompts.insight_prompts import BRIEF_INSIGHT_PROMPT, COMPREHENSIVE_INSIGHT_PROMPT
from app.routers.member_insights import _prompt_for
from app.services.ai import AIService


def test_prompt_for_mode_selects_correct_prompt():
    assert _prompt_for("brief") is BRIEF_INSIGHT_PROMPT
    assert _prompt_for("comprehensive") is COMPREHENSIVE_INSIGHT_PROMPT
    # Unknown mode falls back to comprehensive.
    assert _prompt_for("nonsense") is COMPREHENSIVE_INSIGHT_PROMPT
    assert _prompt_for("") is COMPREHENSIVE_INSIGHT_PROMPT


@pytest.mark.asyncio
async def test_call_ollama_insight_forwards_num_predict_for_brief():
    """Brief mode must thread a lower num_predict cap down to the Ollama call."""
    from unittest.mock import AsyncMock, patch

    # Force local-first so _call_ollama_insight exercises the faked _ollama_chat
    # instead of resolving 'auto'→cloud (which would make a real cloud call).
    with patch(
        "app.core.provider_keys.any_cloud_provider_configured",
        AsyncMock(return_value=False),
    ):
        svc = AIService(db=None)
        captured: dict = {}

        async def fake_chat(model: str, prompt: str, num_predict: int = 4096) -> str:
            captured["num_predict"] = num_predict
            return "generated report"

        svc._ollama_chat = fake_chat  # type: ignore[method-assign]

        await svc._call_ollama_insight("prompt", "ctx", num_predict=1400)
    assert captured["num_predict"] == 1400


@pytest.mark.asyncio
async def test_call_ollama_insight_default_num_predict_is_full():
    from unittest.mock import AsyncMock, patch

    with patch(
        "app.core.provider_keys.any_cloud_provider_configured",
        AsyncMock(return_value=False),
    ):
        svc = AIService(db=None)
        captured: dict = {}

        async def fake_chat(model: str, prompt: str, num_predict: int = 4096) -> str:
            captured["num_predict"] = num_predict
            return "generated report"

        svc._ollama_chat = fake_chat  # type: ignore[method-assign]

        # No num_predict → comprehensive default (4096).
        await svc._call_ollama_insight("prompt", "ctx")
    assert captured["num_predict"] == 4096


@pytest.mark.asyncio
async def test_generate_insight_threads_mode_to_num_predict():
    """generate_insight(mode='brief') should request the brief cap from _call_ollama_insight."""

    class _FakeDB:
        def add(self, obj: object) -> None:
            pass

        async def flush(self) -> None:
            return None

    svc = AIService(db=_FakeDB())
    captured: dict = {}

    async def fake_call(prompt: str, context: str, num_predict: int = 4096) -> tuple[str, str]:
        captured["num_predict"] = num_predict
        return "generated report", "Ollama test"

    svc._call_ollama_insight = fake_call  # type: ignore[method-assign]

    await svc.generate_insight(prompt="p", mode="brief")
    assert captured["num_predict"] == 1400

    await svc.generate_insight(prompt="p", mode="comprehensive")
    assert captured["num_predict"] == 4096
