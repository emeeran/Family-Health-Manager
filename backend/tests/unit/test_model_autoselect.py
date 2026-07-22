"""Unit tests for the startup model auto-tune (services/ai/model_autoselect.py).

Covers the per-provider selectors (economical-capable, newest-then-cheapest),
the household persistence, and the driver with stubbed fetchers — no network,
no real DB.
"""

import json

import pytest

from app.schemas.ai_provider_config import (
    AIProviderConfig,
    DEFAULT_MODELS,
    ProviderConfigItem,
)
from app.schemas.household import FeatureSettings
from app.services.ai import model_autoselect as autoselect


# ── groq ────────────────────────────────────────────────────────────────────


def test_groq_prefers_flagship_70b():
    models = [
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
        "llama-3-8b",
        "llama2-70b-chat",
    ]
    assert autoselect.select_best_model("groq", models) == "llama-3.3-70b-versatile"


def test_groq_next_best_when_flagship_absent():
    # 3.3-70b-versatile absent → fall to the next capable preference entry.
    models = ["llama-3.1-70b-versatile", "llama-3-70b"]
    assert autoselect.select_best_model("groq", models) == "llama-3.1-70b-versatile"


# ── gemini ──────────────────────────────────────────────────────────────────


def test_gemini_picks_newest_flash_and_rejects_pro():
    models = [
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-2.5-pro",  # expensive — must be skipped
        "gemini-1.5-flash",
        "gemini-2.5-flash-001",
    ]
    # 2.5 > 2.0 > 1.5; -001 suffix parses to the same version tuple as bare 2.5,
    # and stable sort keeps the first-seen (2.5-flash) before -001.
    assert autoselect.select_best_model("gemini", models) == "gemini-2.5-flash"


def test_gemini_only_pro_returns_none():
    assert autoselect.select_best_model("gemini", ["gemini-2.5-pro"]) is None


# ── openai ──────────────────────────────────────────────────────────────────


def test_openai_prefers_mini():
    models = ["gpt-4o", "gpt-4o-mini", "gpt-4.1-mini", "text-embedding-3-large"]
    assert autoselect.select_best_model("openai", models) == "gpt-4.1-mini"


def test_openai_excludes_non_chat():
    models = ["text-embedding-3-large", "whisper-1", "dall-e-3", "tts-1"]
    assert autoselect.select_best_model("openai", models) is None


# ── openrouter (rich list with pricing) ─────────────────────────────────────


def test_openrouter_cheapest_capable_ignores_toy_models():
    rich = [
        # Cheapest overall — but a 1B toy, must be EXCLUDED.
        {"id": "meta-llama/llama-3.2-1b-instruct", "prompt_price": 1e-8},
        {"id": "google/gemma-3-4b-it", "prompt_price": 5e-8},
        # Capable & economical — cheapest capable wins.
        {"id": "meta-llama/llama-3.3-70b-instruct", "prompt_price": 9e-8},
        {"id": "qwen/qwen-3-72b-instruct", "prompt_price": 1.2e-7},
    ]
    pick = autoselect.select_best_model("openrouter", rich)
    assert pick == "meta-llama/llama-3.3-70b-instruct"
    assert pick != "meta-llama/llama-3.2-1b-instruct"


def test_openrouter_only_toy_returns_none():
    rich = [
        {"id": "meta-llama/llama-3.2-1b-instruct", "prompt_price": 1e-8},
        {"id": "google/gemma-3-4b-it", "prompt_price": 5e-8},
    ]
    assert autoselect.select_best_model("openrouter", rich) is None


# ── shared edge cases ───────────────────────────────────────────────────────


@pytest.mark.parametrize("provider", ["groq", "gemini", "openai", "openrouter"])
def test_empty_list_returns_none(provider):
    assert autoselect.select_best_model(provider, []) is None


def test_unknown_provider_returns_none():
    assert autoselect.select_best_model("ollama", ["qwen3:4b"]) is None


# ── persistence (_apply_to_households) ──────────────────────────────────────


class _FakeHousehold:
    def __init__(self, settings_json: str):
        self.settings_json = settings_json


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        class _S:
            def __init__(self, items):
                self._items = items

            def all(self):
                return self._items

        return _S(self._items)


class _FakeDB:
    def __init__(self, households):
        self._hh = households
        self.flushed = False

    async def execute(self, _stmt):
        return _FakeResult(self._hh)

    async def flush(self):
        self.flushed = True


def _household_with(models: dict[str, str]) -> _FakeHousehold:
    fs = FeatureSettings(
        ai_providers=AIProviderConfig(
            providers=[ProviderConfigItem(id=pid, enabled=True, model=m) for pid, m in models.items()]
        )
    )
    return _FakeHousehold(fs.model_dump_json())


async def test_apply_updates_cloud_keeps_ollama(monkeypatch):
    hh = _household_with(
        {"groq": "groq-OLD", "gemini": "gemini-OLD", "openrouter": "or-OLD", "ollama": "qwen3:4b"}
    )
    db = _FakeDB([hh])
    chosen = {
        "groq": "llama-3.3-70b-versatile",
        "gemini": "gemini-2.5-flash",
        "openrouter": "meta-llama/llama-3.3-70b-instruct",
        "openai": "gpt-4.1-mini",  # household has no openai item → must NOT add one
    }
    updated = await autoselect._apply_to_households(db, chosen)
    assert updated == 1
    assert db.flushed

    data = json.loads(hh.settings_json)
    providers = {p["id"]: p["model"] for p in data["ai_providers"]["providers"]}
    assert providers["groq"] == "llama-3.3-70b-versatile"
    assert providers["gemini"] == "gemini-2.5-flash"
    assert providers["openrouter"] == "meta-llama/llama-3.3-70b-instruct"
    assert providers["ollama"] == "qwen3:4b"  # untouched
    assert "openai" not in providers  # never adds providers the household didn't enable


async def test_apply_noop_when_household_already_current():
    hh = _household_with({"groq": "llama-3.3-70b-versatile"})
    db = _FakeDB([hh])
    updated = await autoselect._apply_to_households(db, {"groq": "llama-3.3-70b-versatile"})
    assert updated == 0
    assert not db.flushed


# ── driver (refresh_and_autoselect) with stubbed fetchers ───────────────────


async def test_refresh_autoselect_persists_and_mutates_defaults(monkeypatch):
    # Preserve + restore DEFAULT_MODELS so the global mutation doesn't leak.
    saved = dict(DEFAULT_MODELS)

    async def _fake_fetch(pid):
        return {
            "groq": {"groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]},
            "gemini": {"gemini": ["gemini-2.5-flash", "gemini-2.5-pro"]},
            "openai": {"openai": ["gpt-4.1-mini", "gpt-4o"]},
        }.get(pid, {pid: []})

    async def _fake_rich(_client=None):
        return [{"id": "meta-llama/llama-3.3-70b-instruct", "prompt_price": 9e-8}]

    monkeypatch.setattr(autoselect, "fetch_available_models", _fake_fetch)
    monkeypatch.setattr(autoselect, "fetch_openrouter_rich", _fake_rich)

    hh = _household_with(
        {"groq": "groq-OLD", "gemini": "gemini-OLD", "openrouter": "or-OLD", "ollama": "qwen3:4b"}
    )
    db = _FakeDB([hh])

    try:
        chosen = await autoselect.refresh_and_autoselect(db)
    finally:
        DEFAULT_MODELS.clear()
        DEFAULT_MODELS.update(saved)

    assert chosen == {
        "groq": "llama-3.3-70b-versatile",
        "gemini": "gemini-2.5-flash",
        "openrouter": "meta-llama/llama-3.3-70b-instruct",
        "openai": "gpt-4.1-mini",
    }
    data = json.loads(hh.settings_json)
    providers = {p["id"]: p["model"] for p in data["ai_providers"]["providers"]}
    assert providers["groq"] == "llama-3.3-70b-versatile"
    assert providers["ollama"] == "qwen3:4b"


async def test_refresh_autoselect_skips_empty_provider(monkeypatch):
    """A provider that returns [] (no key / failed) is left out of `chosen`."""

    async def _fake_fetch(pid):
        # groq has models; gemini/openai return nothing.
        return {"groq": ["llama-3.3-70b-versatile"]} if pid == "groq" else {pid: []}

    async def _fake_rich(_client=None):
        return []

    monkeypatch.setattr(autoselect, "fetch_available_models", _fake_fetch)
    monkeypatch.setattr(autoselect, "fetch_openrouter_rich", _fake_rich)

    hh = _household_with({"groq": "groq-OLD", "gemini": "gemini-OLD", "ollama": "qwen3:4b"})
    db = _FakeDB([hh])
    chosen = await autoselect.refresh_and_autoselect(db)
    assert chosen == {"groq": "llama-3.3-70b-versatile"}
    # gemini had no candidate → its model is untouched.
    data = json.loads(hh.settings_json)
    providers = {p["id"]: p["model"] for p in data["ai_providers"]["providers"]}
    assert providers["gemini"] == "gemini-OLD"
