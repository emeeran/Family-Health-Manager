"""Unit tests for the sequential extraction provider chain.

Exercises ``call_text_extraction`` → ``_run_provider_chain``: providers are
tried in the configured plan's order, the first non-empty result wins,
exceptions/timeouts fall through to the next, and the local Ollama entry is
exempt from the short failover timeout. Also covers the config-driven ordering
introduced when extraction was unified onto the household provider config: the
plan honours ``primary_provider`` (local vs cloud first), ``enabled`` flags, the
per-provider ``model``, and the Gemini auth preference. All provider functions
are mocked — no network.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import app.services.ai.document_extractor as dex
from app.schemas.ai_provider_config import AIProviderConfig, ProviderConfigItem
from app.services.ai.document_extractor import ExtractionProviderPlan

JSON_OK = '{"record_type": "lab_report"}'


def _plan(primary: str = "cloud", **item_overrides) -> ExtractionProviderPlan:
    """Build a plan with all five providers; ``primary`` sets the group order.

    ``item_overrides`` maps provider id → model (empty string keeps the default
    model unset so no ``model`` kwarg is passed to the mock).
    """
    cfg = AIProviderConfig(
        providers=[
            ProviderConfigItem(id="groq", enabled=True, model=item_overrides.get("groq", "")),
            ProviderConfigItem(
                id="openrouter", enabled=True, model=item_overrides.get("openrouter", "")
            ),
            ProviderConfigItem(id="gemini", enabled=True, model=item_overrides.get("gemini", "")),
            ProviderConfigItem(id="openai", enabled=True, model=item_overrides.get("openai", "")),
            ProviderConfigItem(id="ollama", enabled=True, model=item_overrides.get("ollama", "")),
        ],
        primary_provider=primary,  # type: ignore[arg-type]
    )
    return ExtractionProviderPlan.from_config(cfg)


# ---- Chain mechanics (cloud-first plan, Groq → … → Ollama) ----


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
        out = await dex.call_text_extraction("pdf text", ref, _plan())
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
        out = await dex.call_text_extraction("pdf text", ref, _plan())
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
        out = await dex.call_text_extraction("pdf text", ref, _plan())
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
        out = await dex.call_text_extraction("pdf text", ref, _plan())
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
        out = await dex.call_text_extraction("pdf text", [""], _plan())
    assert out is None


# ---- Config-driven ordering (Part 2a unification) ----


async def test_local_first_plan_tries_ollama_before_cloud():
    """primary=local → Ollama is first; a working Ollama skips all cloud calls."""
    ollama = AsyncMock(return_value=JSON_OK)
    groq = AsyncMock(return_value="should not be reached")
    with (
        patch.object(dex, "call_ollama_text", ollama),
        patch.object(dex, "call_groq_text", groq),
        patch.object(dex, "call_openrouter_text", AsyncMock()),
        patch.object(dex, "call_gemini_text", AsyncMock()),
        patch.object(dex, "call_openai_text", AsyncMock()),
    ):
        ref = [""]
        out = await dex.call_text_extraction("pdf text", ref, _plan(primary="local"))
    assert out == JSON_OK
    assert ref[0] == "Ollama text"
    groq.assert_not_called()


async def test_disabled_providers_are_skipped():
    cfg = AIProviderConfig(
        providers=[
            ProviderConfigItem(id="groq", enabled=False, model=""),
            ProviderConfigItem(id="gemini", enabled=True, model=""),
            ProviderConfigItem(id="ollama", enabled=True, model=""),
        ],
        primary_provider="cloud",  # type: ignore[arg-type]
    )
    plan = ExtractionProviderPlan.from_config(cfg)
    groq = AsyncMock(return_value="should not be reached")
    gemini = AsyncMock(return_value=JSON_OK)
    with (
        patch.object(dex, "call_groq_text", groq),
        patch.object(dex, "call_gemini_text", gemini),
        patch.object(dex, "call_ollama_text", AsyncMock()),
    ):
        ref = [""]
        out = await dex.call_text_extraction("pdf text", ref, plan)
    assert out == JSON_OK
    assert ref[0] == "Gemini text"
    groq.assert_not_called()  # disabled → never tried


async def test_per_provider_model_is_passed():
    """The configured model reaches the provider callable."""
    gemini = AsyncMock(return_value=JSON_OK)
    with (
        patch.object(dex, "call_groq_text", AsyncMock(side_effect=RuntimeError)),
        patch.object(dex, "call_openrouter_text", AsyncMock(side_effect=RuntimeError)),
        patch.object(dex, "call_gemini_text", gemini),
        patch.object(dex, "call_openai_text", AsyncMock()),
        patch.object(dex, "call_ollama_text", AsyncMock()),
    ):
        await dex.call_text_extraction("pdf text", [""], _plan(gemini="gemini-2.5-pro"))
    # The partial bound the model kwarg through to the call.
    assert gemini.call_args.kwargs.get("model") == "gemini-2.5-pro"


async def test_gemini_auth_preference_propagates():
    gemini = AsyncMock(return_value=JSON_OK)
    with (
        patch.object(dex, "call_groq_text", AsyncMock(side_effect=RuntimeError)),
        patch.object(dex, "call_openrouter_text", AsyncMock(side_effect=RuntimeError)),
        patch.object(dex, "call_gemini_text", gemini),
        patch.object(dex, "call_openai_text", AsyncMock()),
        patch.object(dex, "call_ollama_text", AsyncMock()),
    ):
        plan = ExtractionProviderPlan.from_config(
            AIProviderConfig(
                providers=[ProviderConfigItem(id="gemini", enabled=True, model="")],
                primary_provider="cloud",  # type: ignore[arg-type]
                gemini_auth="adc",
            )
        )
        await dex.call_text_extraction("pdf text", [""], plan)
    assert gemini.call_args.kwargs.get("gemini_auth") == "adc"


async def test_ollama_uses_json_grammar_for_extraction():
    """Structured extraction constrains Ollama to JSON (fmt='json')."""
    ollama = AsyncMock(return_value=JSON_OK)
    with (
        patch.object(dex, "call_ollama_text", ollama),
        patch.object(dex, "call_groq_text", AsyncMock()),
        patch.object(dex, "call_openrouter_text", AsyncMock()),
        patch.object(dex, "call_gemini_text", AsyncMock()),
        patch.object(dex, "call_openai_text", AsyncMock()),
    ):
        await dex.call_text_extraction("pdf text", [""], _plan(primary="local"))
    assert ollama.call_args.kwargs.get("fmt") == "json"


def test_cache_fingerprint_changes_with_order_or_model():
    base = _plan(primary="cloud")
    flipped = _plan(primary="local")
    reindexed = ExtractionProviderPlan.from_config(
        AIProviderConfig(
            providers=[
                ProviderConfigItem(id="gemini", enabled=True, model=""),
                ProviderConfigItem(id="groq", enabled=True, model=""),
                ProviderConfigItem(id="ollama", enabled=True, model=""),
            ],
            primary_provider="cloud",  # type: ignore[arg-type]
        )
    )
    assert base.cache_fingerprint() != flipped.cache_fingerprint()  # primary group
    assert base.cache_fingerprint() != reindexed.cache_fingerprint()  # array order
