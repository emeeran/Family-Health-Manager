"""Startup auto-tune of cloud AI provider models.

On boot, refresh each cloud provider's model list and set the latest,
most-economical model that's still capable for medical extraction / chat /
insights. Ollama is excluded (local, free-text, user-managed).

Selection is **economical-capable, newest-then-cheapest**: each provider has a
curated notion of its cheap-but-capable tier, and among capable candidates the
newest (then cheapest, where pricing is available) wins. Groq / Gemini / OpenAI
don't expose pricing, so "economical" there IS the tier (Groq 70b-versatile,
Gemini ``-flash``, OpenAI ``*-mini``); OpenRouter exposes real pricing, so it
ranks the capable allowlist by prompt price.

Rationale: raw price-ranking lands on 1B–7B toy models (``llama-3.2-1b``,
``gemma-3-4b``) that would butcher medical extraction — a capability floor is
required, not a luxury.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from sqlalchemy import select

from app.models.base import Household
from app.schemas.household import FeatureSettings
from app.services.ai.model_fetcher import fetch_available_models, fetch_openrouter_rich

logger = logging.getLogger(__name__)

# Cloud providers that get auto-tuned. Ollama is excluded (local free-text).
CLOUD_PROVIDERS = ["groq", "gemini", "openrouter", "openai"]


# ── per-provider capability/economy heuristics ─────────────────────────────

# Groq: small curated catalog, no pricing. Preference = newest capable-economical
# (70B-class before the weaker 8B instant — both are Groq's cheap tier, but 70B
# is far more capable for medical extraction).
_GROQ_PREFERENCE = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "llama-3-70b-versatile",
    "llama-3-70b",
    "llama-3.1-8b-instant",
    "llama-3-8b",
]

# OpenAI: economical-capable = mini/nano. Preference order.
_OPENAI_PREFERENCE = ["gpt-4.1-mini", "gpt-4o-mini", "gpt-4.1-nano", "gpt-4.1"]
_OPENAI_NONCHAT = re.compile(
    r"(embed|dall|e-|whisper|tts|ada|babbage|curie|davinci|moderation|realtime|audio|omni-moderation)",
    re.I,
)

# Gemini: economical = -flash. Match gemini-<version>-flash[-suffix], exclude
# pro/thinking/vision/embedding/tts/etc.
_GEMINI_FLASH_RE = re.compile(r"^gemini-(\d+(?:\.\d+)+)-flash(?:-001|-latest)?$", re.I)
_GEMINI_NONTEXT = re.compile(
    r"(pro|thinking|vision|embedding|tts|learning|aqa|live|imagen)", re.I
)

# OpenRouter: capability floor = curated capable families (≥~30B / strong
# mid-tier). Among matches, rank by prompt price (cheapest wins).
_OPENROUTER_CAPABLE = re.compile(
    r"(?:"
    r"meta-llama/llama-3\.(?:3|1)-70b-instruct"
    r"|google/gemini-\d+(?:\.\d+)+-flash"
    r"|deepseek/deepseek-(?:v3|v4|chat|r1)"
    r"|qwen/qwen-(?:2\.5|3)-(?:72b|32b)"
    r"|mistralai/mistral-large"
    r"|microsoft/phi-4"
    r"|openai/gpt-oss-120b"
    r")",
    re.I,
)


def _version_key(model_id: str) -> tuple[int, ...]:
    """Comparable version tuple from a model id (e.g. 'gemini-2.5-flash' → (2, 5)).

    Takes the first dotted version run only, so a pinned snapshot suffix
    (``-001``/``-latest``) doesn't outrank the bare latest alias on a tie.
    """
    m = re.search(r"(\d+(?:\.\d+)+)", model_id)
    if not m:
        return (0,)
    return tuple(int(n) for n in m.group(1).split("."))


def _select_groq(models: list[str]) -> str | None:
    present = {m.lower(): m for m in models}
    for pref in _GROQ_PREFERENCE:
        if pref in present:
            return present[pref]
    # Fallback: newest llama-3.* in the catalog.
    llama = [m for m in models if re.search(r"llama-3", m, re.I)]
    llama.sort(key=_version_key, reverse=True)
    return llama[0] if llama else None


def _select_gemini(models: list[str]) -> str | None:
    flashes = [m for m in models if _GEMINI_FLASH_RE.match(m) and not _GEMINI_NONTEXT.search(m)]
    flashes.sort(key=_version_key, reverse=True)
    return flashes[0] if flashes else None


def _select_openai(models: list[str]) -> str | None:
    present = {m.lower(): m for m in models}
    for pref in _OPENAI_PREFERENCE:
        if pref in present:
            return present[pref]
    # Fallback: newest gpt-4.* mini/nano that isn't a non-chat model.
    mini = [
        m
        for m in models
        if re.search(r"gpt-4", m, re.I)
        and re.search(r"mini|nano", m, re.I)
        and not _OPENAI_NONCHAT.search(m)
    ]
    mini.sort(key=_version_key, reverse=True)
    return mini[0] if mini else None


def _select_openrouter(rich: list[dict]) -> str | None:
    capable = [m for m in rich if m.get("id") and _OPENROUTER_CAPABLE.search(m["id"])]
    if not capable:
        return None
    # Stable sort: newest first, then cheapest — so equal price keeps the newest.
    capable.sort(key=lambda m: _version_key(m["id"]), reverse=True)
    capable.sort(key=lambda m: m.get("prompt_price", 0.0))
    return capable[0]["id"]


def select_best_model(provider: str, models: list[Any]) -> str | None:
    """Pick the latest economical-capable model for ``provider``.

    ``models`` is a list of id strings for groq/gemini/openai, and the **rich**
    list of dicts (with ``prompt_price``) for openrouter. Returns ``None`` when
    the list is empty or holds no capable candidate — the caller leaves the
    config unchanged in that case.
    """
    if not models:
        return None
    if provider == "groq":
        return _select_groq(models)
    if provider == "gemini":
        return _select_gemini(models)
    if provider == "openai":
        return _select_openai(models)
    if provider == "openrouter":
        return _select_openrouter(models)
    return None


# ── persistence ────────────────────────────────────────────────────────────


def _parse_feature_settings(household: Household) -> FeatureSettings:
    """Parse settings_json into FeatureSettings, falling back to defaults."""
    if household.settings_json:
        try:
            return FeatureSettings(**json.loads(household.settings_json))
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return FeatureSettings()


async def _apply_to_households(db, chosen: dict[str, str]) -> int:
    """Set chosen models on every household's existing cloud providers.

    Only updates ``ProviderConfigItem``s already present in a household's config
    (never adds providers the household didn't enable). Returns the number of
    households whose config changed. Caller commits.
    """
    result = await db.execute(select(Household))
    households = result.scalars().all()
    updated = 0
    for hh in households:
        settings = _parse_feature_settings(hh)
        changed = False
        for item in settings.ai_providers.providers:
            if item.id in chosen and item.model != chosen[item.id]:
                item.model = chosen[item.id]
                changed = True
        if changed:
            hh.settings_json = settings.model_dump_json()
            updated += 1
    if updated:
        await db.flush()
    return updated


async def refresh_and_autoselect(db) -> dict[str, str]:
    """Fetch each cloud provider's models and set the best one in every household.

    Mutates the runtime ``DEFAULT_MODELS`` (so new households inherit the picks)
    and persists into each existing household's ``settings_json``. Ollama is
    never changed. Providers with no key / that fail / with no capable model are
    left untouched (logged). Returns ``{provider: chosen_model}``.
    """
    from app.schemas.ai_provider_config import DEFAULT_MODELS

    # OpenRouter needs the rich (priced) list; the others are id-only.
    lists: dict[str, list] = {}
    async with httpx.AsyncClient(timeout=10) as client:
        for pid in ("groq", "gemini", "openai"):
            try:
                lists[pid] = (await fetch_available_models(pid)).get(pid, [])
            except Exception as exc:  # noqa: BLE001 — one dead provider can't abort the rest
                logger.warning("Model fetch failed for %s: %s", pid, exc)
                lists[pid] = []
        try:
            lists["openrouter"] = await fetch_openrouter_rich(client)
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenRouter model fetch failed: %s", exc)
            lists["openrouter"] = []

    chosen: dict[str, str] = {}
    for pid in CLOUD_PROVIDERS:
        try:
            pick = select_best_model(pid, lists.get(pid, []))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Model selection failed for %s: %s", pid, exc)
            pick = None
        if pick:
            chosen[pid] = pick
            DEFAULT_MODELS[pid] = pick
        else:
            logger.info("Model auto-tune: no suitable %s model found (left unchanged)", pid)

    if chosen:
        updated = await _apply_to_households(db, chosen)
        logger.info("Model auto-tune applied to %d household(s)", updated)
    return chosen
