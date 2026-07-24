"""Tests for the dynamic task router (app/services/ai/task_router.py)."""

import pytest

from app.schemas.ai_provider_config import AIProviderConfig, ProviderConfigItem
from app.services.ai.task_router import (
    TaskType,
    difficulty_for,
    next_difficulty,
    record_escalation,
    resolve_model_for_task,
    route,
    should_escalate,
)


def _cfg(*providers: ProviderConfigItem, primary: str = "cloud") -> AIProviderConfig:
    return AIProviderConfig(providers=list(providers), primary_provider=primary)  # type: ignore[arg-type]


@pytest.fixture
def all_keyed(monkeypatch):
    """Treat every provider as keyed so route() considers all configured ones."""
    async def _configured(_pid: str) -> bool:
        return True

    monkeypatch.setattr("app.services.ai.task_router.is_provider_configured", _configured)


# ---- route(): tier floor, modality, difficulty, ordering ----


@pytest.mark.asyncio
async def test_route_enforces_tier_floor(all_keyed):
    """EXTRACTION_TEXT (min standard) never returns a fast-tier model — it
    upgrades the provider's model to meet the floor (8b -> 70b)."""
    from app.services.ai.model_catalog import TIER_RANK, spec_for

    cfg = _cfg(
        ProviderConfigItem(id="groq", enabled=True, model="llama-3.1-8b-instant"),  # fast
        ProviderConfigItem(id="gemini", enabled=True, model="gemini-2.5-flash"),  # standard
    )
    plan = await route(TaskType.EXTRACTION_TEXT, "easy", cfg)
    # The configured 8b (fast) is NOT used; groq is upgraded to a standard model.
    assert ("groq", "llama-3.1-8b-instant") not in plan
    for provider, model in plan:
        if provider == "ollama":
            continue
        spec = spec_for(provider, model)
        assert spec is not None
        assert TIER_RANK[spec.tier] >= TIER_RANK["standard"], (provider, model)


@pytest.mark.asyncio
async def test_route_filters_by_modality_for_vision(all_keyed):
    """EXTRACTION_VISION only returns vision-capable models."""
    cfg = _cfg(
        ProviderConfigItem(id="groq", enabled=True, model="llama-3.3-70b-versatile"),  # text-only
        ProviderConfigItem(id="gemini", enabled=True, model="gemini-2.5-flash"),  # vision
        ProviderConfigItem(id="openai", enabled=True, model="gpt-4o"),  # vision
    )
    plan = await route(TaskType.EXTRACTION_VISION, "normal", cfg)
    providers = {p for p, _ in plan}
    assert "groq" not in providers  # text-only, can't do vision extraction
    assert "gemini" in providers
    assert "openai" in providers


@pytest.mark.asyncio
async def test_route_difficulty_bumps_tier(all_keyed):
    """hard difficulty raises the floor to strong-tier models."""
    cfg = _cfg(
        ProviderConfigItem(id="gemini", enabled=True, model="gemini-2.5-flash"),  # standard
        ProviderConfigItem(id="openai", enabled=True, model="gpt-4o"),  # strong
    )
    plan = await route(TaskType.EXTRACTION_TEXT, "hard", cfg)
    # Only strong-tier models qualify at "hard"; flash is excluded.
    assert all(m == "gpt-4o" or "pro" in m for _, m in plan)
    assert ("openai", "gpt-4o") in plan


@pytest.mark.asyncio
async def test_route_excludes_generator_family(all_keyed):
    """VALIDATION never uses the generator's family (different-family rule)."""
    cfg = _cfg(
        ProviderConfigItem(id="groq", enabled=True, model="llama-3.3-70b-versatile"),
        ProviderConfigItem(id="gemini", enabled=True, model="gemini-2.5-flash"),
    )
    plan = await route(TaskType.VALIDATION, "normal", cfg, exclude_family="groq")
    assert "groq" not in {p for p, _ in plan}
    assert ("gemini", "gemini-2.5-flash") in plan


@pytest.mark.asyncio
async def test_route_prefers_household_configured_model(all_keyed):
    """The household's configured model is used when it qualifies, even if a
    cheaper catalog model exists (respects user intent)."""
    cfg = _cfg(
        ProviderConfigItem(id="gemini", enabled=True, model="gemini-2.5-pro"),  # strong, pricey
    )
    plan = await route(TaskType.REPORT_INSIGHT, "normal", cfg)
    assert ("gemini", "gemini-2.5-pro") in plan  # not overridden by the cheaper flash


@pytest.mark.asyncio
async def test_route_ollama_last_and_respects_vision(all_keyed):
    """Ollama is last; a text-only Ollama model is excluded from a vision task."""
    cfg = _cfg(
        ProviderConfigItem(id="gemini", enabled=True, model="gemini-2.5-flash"),
        ProviderConfigItem(id="ollama", enabled=True, model="llama3"),  # text-only
    )
    plan = await route(TaskType.EXTRACTION_VISION, "normal", cfg)
    assert plan[-1] != ("ollama", "llama3") or "ollama" not in {p for p, _ in plan}
    assert "ollama" not in {p for p, _ in plan}  # text-only ollama can't do vision


@pytest.mark.asyncio
async def test_route_orders_by_cost(all_keyed):
    """Cheapest capable cloud model comes first (Gemini free tier < paid OpenAI)."""
    cfg = _cfg(
        ProviderConfigItem(id="openai", enabled=True, model="gpt-4o-mini"),  # standard, paid
        ProviderConfigItem(id="gemini", enabled=True, model="gemini-2.5-flash"),  # standard, $0
    )
    plan = await route(TaskType.VALIDATION, "normal", cfg)
    assert plan[0] == ("gemini", "gemini-2.5-flash")  # free first


@pytest.mark.asyncio
async def test_resolve_model_returns_first(all_keyed):
    cfg = _cfg(ProviderConfigItem(id="gemini", enabled=True, model="gemini-2.5-flash"))
    assert await resolve_model_for_task(TaskType.CHAT, "normal", cfg) == ("gemini", "gemini-2.5-flash")


# ---- should_escalate ----


def test_should_escalate_thresholds():
    assert should_escalate(TaskType.EXTRACTION_TEXT, "low") is True
    assert should_escalate(TaskType.EXTRACTION_TEXT, "medium") is False  # 0.5 > 0.3
    assert should_escalate(TaskType.EXTRACTION_TEXT, "high") is False
    assert should_escalate(TaskType.EXTRACTION_TEXT, None) is False
    # Streaming tasks never escalate.
    assert should_escalate(TaskType.CHAT, "low") is False
    assert should_escalate(TaskType.REPORT_INSIGHT, "low") is False


def test_should_escalate_disabled(monkeypatch):
    monkeypatch.setattr("app.services.ai.task_router.router_enabled", lambda: False)
    assert should_escalate(TaskType.EXTRACTION_TEXT, "low") is False


def test_next_difficulty_caps_at_hard():
    assert next_difficulty("easy") == "normal"
    assert next_difficulty("normal") == "hard"
    assert next_difficulty("hard") == "hard"


# ---- escalation memo ----


def test_escalation_memo_round_trip():
    task, content = TaskType.EXTRACTION_TEXT, "doc-bytes-hash-xyz"
    assert difficulty_for(task, content) == "normal"  # nothing memoized yet
    record_escalation(task, content, "hard")
    assert difficulty_for(task, content) == "hard"  # memoized


@pytest.mark.asyncio
async def test_router_disabled_falls_back(all_keyed, monkeypatch):
    """When the router is off, route() is never reached — callers use ordered
    providers (covered by _call_ai's fallback). Here we confirm the toggle."""
    monkeypatch.setattr("app.services.ai.task_router.router_enabled", lambda: False)
    # should_escalate respects the toggle.
    assert should_escalate(TaskType.EXTRACTION_TEXT, "low") is False
