"""Tests for the Phase 1-6 document-processing speedup overhaul.

Covers:
* C1 — primary_provider "auto" resolves cloud-first when a key is configured.
* A1 — provider-health negative cache prunes confirmed-dead providers (no-op
  until a probe populates it, so existing sequential semantics are preserved).
* A2 — opt-in provider racing (default off = sequential).
* B2 — multi-image vision callables + configurable pages-per-chunk.
* B4 — OLLAMA_FAST_MODEL overrides the Ollama text entry and is in the fingerprint.
* D2/D4 — _provider_health_hint summarises a probe for the upload UI.

All provider functions are mocked — no network.
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import app.services.ai.document_extractor as dex
import app.services.ai.provider_health as ph
from app.schemas.ai_provider_config import (
    AIProviderConfig,
    ProviderConfigItem,
    default_provider_config,
    ordered_providers,
    resolve_primary_provider,
)
from app.services.ai.document_extractor import ExtractionProviderPlan

JSON_OK = '{"record_type": "lab_report"}'


def _plan(primary: str = "cloud") -> ExtractionProviderPlan:
    cfg = AIProviderConfig(
        providers=[ProviderConfigItem(id=p, enabled=True, model="") for p in
                   ("groq", "openrouter", "gemini", "openai", "ollama")],
        primary_provider=primary,  # type: ignore[arg-type]
    )
    return ExtractionProviderPlan.from_config(cfg)


# ---- C1: primary_provider "auto" ----


async def test_resolve_auto_primary_is_cloud_when_key_configured(monkeypatch):
    monkeypatch.setattr(
        "app.core.provider_keys.any_cloud_provider_configured",
        AsyncMock(return_value=True),
    )
    cfg = AIProviderConfig(
        providers=[ProviderConfigItem(id="ollama", enabled=True, model="")],
        primary_provider="auto",  # type: ignore[arg-type]
    )
    assert await resolve_primary_provider(cfg) == "cloud"


async def test_resolve_auto_primary_is_local_when_no_key(monkeypatch):
    monkeypatch.setattr(
        "app.core.provider_keys.any_cloud_provider_configured",
        AsyncMock(return_value=False),
    )
    cfg = AIProviderConfig(
        providers=[ProviderConfigItem(id="ollama", enabled=True, model="")],
        primary_provider="auto",  # type: ignore[arg-type]
    )
    assert await resolve_primary_provider(cfg) == "local"


def test_ordered_providers_auto_falls_back_to_local_first():
    """An unresolved 'auto' (sync fallback) orders local-first."""
    cfg = AIProviderConfig(
        providers=[ProviderConfigItem(id="groq", enabled=True, model=""),
                   ProviderConfigItem(id="ollama", enabled=True, model="")],
        primary_provider="auto",  # type: ignore[arg-type]
    )
    assert [p.id for p in ordered_providers(cfg)] == ["ollama", "groq"]


def test_default_config_is_auto():
    assert default_provider_config().primary_provider == "auto"


# ---- A1: provider-health negative cache + pruning ----


def test_known_dead_empty_without_probe():
    ph.clear()
    assert ph.known_dead_providers() == set()
    assert ph.is_known_dead("groq") is False


def test_prune_is_noop_when_no_probe():
    ph.clear()
    plan = ExtractionProviderPlan.from_config(default_provider_config())
    assert plan.prune_known_dead() is plan  # unchanged — full chain retained


def test_prune_removes_confirmed_dead_keeps_rest():
    ph.clear()
    ph._state["result"] = {"groq": False, "openrouter": False}
    ph._state["expires_at"] = time.monotonic() + 60
    plan = ExtractionProviderPlan.from_config(default_provider_config())
    pruned = plan.prune_known_dead()
    ids = {it.provider_id for it in pruned.items}
    assert "groq" not in ids
    assert "openrouter" not in ids
    assert {"gemini", "openai", "ollama"} <= ids


def test_prune_never_empties_the_chain():
    ph.clear()
    ph._state["result"] = {p: False for p in ("groq", "openrouter", "gemini", "openai", "ollama")}
    ph._state["expires_at"] = time.monotonic() + 60
    plan = ExtractionProviderPlan.from_config(default_provider_config())
    pruned = plan.prune_known_dead()
    assert len(pruned.items) >= 1  # would-be-empty falls back to the full chain


def test_prune_ignores_expired_probe():
    ph.clear()
    ph._state["result"] = {"groq": False}
    ph._state["expires_at"] = time.monotonic() - 1  # expired
    plan = ExtractionProviderPlan.from_config(default_provider_config())
    assert plan.prune_known_dead() is plan


# ---- A2: opt-in provider racing ----


async def test_race_off_is_strictly_sequential():
    """Default (race off): Groq wins, OpenRouter never called."""
    groq = AsyncMock(return_value=JSON_OK)
    with (
        patch.object(dex, "call_groq_text", groq),
        patch.object(dex, "call_openrouter_text", AsyncMock(return_value="x")),
        patch.object(dex, "call_gemini_text", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_text", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_text", AsyncMock(return_value=None)),
    ):
        ref = [""]
        out = await dex.call_text_extraction("pdf text", ref, _plan("cloud"))
    assert out == JSON_OK
    assert ref[0] == "Groq text"


async def test_race_on_picks_fastest_cloud(monkeypatch):
    """Race on: a fast OpenRouter beats a slow Groq; both cloud entries are fired."""
    monkeypatch.setattr(dex.settings, "EXTRACTION_RACE_PROVIDERS", True)

    async def groq_slow(*_a, **_kw):
        await asyncio.sleep(0.4)
        return '{"record_type": "from_groq"}'

    async def or_fast(*_a, **_kw):
        return JSON_OK

    openrouter = AsyncMock(side_effect=or_fast)
    with (
        patch.object(dex, "call_groq_text", AsyncMock(side_effect=groq_slow)),
        patch.object(dex, "call_openrouter_text", openrouter),
        patch.object(dex, "call_gemini_text", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_text", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_text", AsyncMock(return_value=None)),
    ):
        ref = [""]
        out = await dex.call_text_extraction("pdf text", ref, _plan("cloud"))
    assert out == JSON_OK
    assert ref[0] == "OpenRouter text"  # faster cloud entry won the race


async def test_race_falls_through_to_local_when_all_cloud_fail(monkeypatch):
    monkeypatch.setattr(dex.settings, "EXTRACTION_RACE_PROVIDERS", True)
    with (
        patch.object(dex, "call_groq_text", AsyncMock(side_effect=RuntimeError)),
        patch.object(dex, "call_openrouter_text", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_text", AsyncMock(side_effect=RuntimeError)),
        patch.object(dex, "call_openai_text", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_text", AsyncMock(return_value=JSON_OK)),
    ):
        ref = [""]
        out = await dex.call_text_extraction("pdf text", ref, _plan("local"))
    assert out == JSON_OK
    assert ref[0] == "Ollama text"


# ---- B2: multi-image vision ----


def test_vision_multi_entries_resolve_all_providers():
    plan = ExtractionProviderPlan.from_config(default_provider_config())
    labels = {e.label for e in plan.vision_multi_entries()}
    assert "Groq vision_multi" in labels
    assert "Gemini vision_multi" in labels


async def test_call_vision_multi_passes_image_list_to_provider():
    groq_multi = AsyncMock(return_value=JSON_OK)
    with (
        patch.object(dex, "call_groq_vision_multi", groq_multi),
        patch.object(dex, "call_openrouter_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_gemini_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_openai_vision_multi", AsyncMock(return_value=None)),
        patch.object(dex, "call_ollama_vision_multi", AsyncMock(return_value=None)),
    ):
        out = await dex.call_vision_provider_from_b64_multi(
            ["imgA", "imgB"], "image/jpeg", [""], _plan("cloud")
        )
    assert out == JSON_OK
    # First positional arg the provider received is the image LIST.
    assert groq_multi.call_args.args[0] == ["imgA", "imgB"]


async def test_call_vision_multi_returns_none_for_empty_list():
    assert await dex.call_vision_provider_from_b64_multi(
        [], "image/jpeg", [""], _plan("cloud")
    ) is None


# ---- B2: pages_per_chunk configurable ----


def test_chunk_ocr_text_respects_pages_per_chunk():
    pages = "\n\n".join(f"--- Page {i} ---\npage {i} content" for i in range(1, 7))
    assert len(dex.chunk_ocr_text(pages, pages_per_chunk=2)) == 3
    assert len(dex.chunk_ocr_text(pages, pages_per_chunk=6)) == 1


# ---- B4: OLLAMA_FAST_MODEL ----


def test_fast_model_overrides_ollama_text_entry_only(monkeypatch):
    monkeypatch.setattr(dex.settings, "OLLAMA_FAST_MODEL", "qwen3:1.7b")
    plan = ExtractionProviderPlan.from_config(default_provider_config())
    text_ollama = next(e for e in plan.text_entries(json_grammar=True) if e.label == "Ollama text")
    vision_ollama = next(
        e for e in plan.vision_entries(json_grammar=True) if e.label == "Ollama vision"
    )
    # Text extraction uses the fast model; vision keeps the plan model.
    assert text_ollama.fn.keywords.get("model") == "qwen3:1.7b"
    assert vision_ollama.fn.keywords.get("model") != "qwen3:1.7b"


def test_fast_model_changes_cache_fingerprint(monkeypatch):
    monkeypatch.setattr(dex.settings, "OLLAMA_FAST_MODEL", "")
    without = ExtractionProviderPlan.from_config(default_provider_config()).cache_fingerprint()
    monkeypatch.setattr(dex.settings, "OLLAMA_FAST_MODEL", "qwen3:1.7b")
    with_fast = ExtractionProviderPlan.from_config(default_provider_config()).cache_fingerprint()
    assert without != with_fast


# ---- D2/D4: provider health hint ----


def _hint_cfg(*ids: str) -> AIProviderConfig:
    return AIProviderConfig(
        providers=[ProviderConfigItem(id=i, enabled=True, model="") for i in ids],
        primary_provider="cloud",  # type: ignore[arg-type]
    )


def test_health_hint_cloud_ready():
    from app.routers.health_records import _provider_health_hint

    hint = _provider_health_hint(
        {"groq": True, "openrouter": False, "ollama": True}, _hint_cfg("groq", "openrouter", "ollama")
    )
    assert hint is not None
    assert hint["cloud_ready"] is True
    assert hint["providers_ready"] == 2
    assert hint["providers_total"] == 3


def test_health_hint_local_only_warns_slow():
    from app.routers.health_records import _provider_health_hint

    hint = _provider_health_hint(
        {"groq": False, "ollama": True}, _hint_cfg("groq", "ollama")
    )
    assert hint is not None
    assert hint["cloud_ready"] is False
    assert "local CPU" in hint["detail"]


def test_health_hint_none_ready():
    from app.routers.health_records import _provider_health_hint

    hint = _provider_health_hint(
        {"groq": False, "ollama": False}, _hint_cfg("groq", "ollama")
    )
    assert hint is not None
    assert hint["providers_ready"] == 0
    assert "No providers ready" in hint["detail"]


def test_health_hint_none_when_no_probe():
    from app.routers.health_records import _provider_health_hint

    assert _provider_health_hint({}, _hint_cfg("groq")) is None
    assert _provider_health_hint(None, _hint_cfg("groq")) is None  # type: ignore[arg-type]
