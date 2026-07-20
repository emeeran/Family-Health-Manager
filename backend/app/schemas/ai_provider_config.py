"""AI provider configuration schemas."""

from typing import Literal

from pydantic import BaseModel

from app.core.config import get_settings

settings = get_settings()

PROVIDER_LABELS: dict[str, str] = {
    "ollama": "Ollama (local)",
    "openrouter": "OpenRouter",
    "groq": "Groq",
    "gemini": "Google Gemini",
    "openai": "OpenAI",
}

AVAILABLE_MODELS: dict[str, list[str]] = {
    "ollama": [],  # empty = free-text input
    "openrouter": ["deepseek/deepseek-v4-flash", "google/gemini-2.5-flash-preview"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    "openai": ["gpt-5.4-mini", "gpt-5.4-nano", "gpt-4o", "gpt-4o-mini"],
}

DEFAULT_MODELS: dict[str, str] = {
    "ollama": settings.OLLAMA_TEXT_MODEL,
    "openrouter": "deepseek/deepseek-v4-flash",
    "groq": "llama-3.3-70b-versatile",
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-5.4-mini",
}

DEFAULT_ORDER: list[str] = ["groq", "gemini", "ollama"]
# Groq (fastest free cloud) → Gemini (broad capability + ADC) → Ollama (local
# CPU fallback). OpenRouter and OpenAI remain available (AVAILABLE_MODELS /
# DEFAULT_MODELS / the Settings UI) but are opt-in — the default chain keeps
# extraction fast and free for a freshly-keyed household, with local as the
# last resort. ``primary_provider="auto"`` tries the cloud group first when any
# cloud key is configured, else local; see ``ordered_providers``.


class ProviderConfigItem(BaseModel):
    """Configuration for a single AI provider."""

    id: str
    enabled: bool = True
    model: str = ""


class AIProviderConfig(BaseModel):
    """Provider configuration: ordered list + which group (cloud/local) to try first.

    ``providers`` array order is the failover order *within* each group;
    ``primary_provider`` decides whether the local (Ollama) or cloud group is
    tried first, with the other as automatic fallback.

    ``primary_provider="auto"`` (the default for new configs) prefers cloud when
    any cloud provider has a key configured, otherwise local. This makes a
    freshly-keyed household 30-60x faster (cloud ~1-2s/doc vs CPU Ollama
    ~60-120s) with zero config, while an Ollama-only box (no keys) is
    unaffected (still local-first). The resolution happens at call time via
    :func:`resolve_primary_provider`; :func:`ordered_providers` treats an
    unresolved "auto" as local-first (its sync, safe fallback).

    ``gemini_auth`` is the Gemini-specific auth preference (Auto / ADC / API Key)
    surfaced as a dropdown on the Gemini provider row in Settings. "auto" keeps
    the original behaviour (ADC when a credentials file + project are configured
    on the server, else API key).
    """

    providers: list[ProviderConfigItem]
    primary_provider: Literal["auto", "cloud", "local"] = "auto"
    gemini_auth: Literal["auto", "adc", "api_key"] = "auto"


class AIProviderConfigResponse(BaseModel):
    """Response including config plus static metadata for the frontend."""

    config: AIProviderConfig
    available_models: dict[str, list[str]]
    provider_labels: dict[str, str]
    # True when the server has a readable Gemini ADC file + Vertex project, so
    # the frontend can enable the "ADC" auth option (and warn when it's off).
    adc_available: bool = False


def default_provider_config() -> AIProviderConfig:
    """Return the default provider configuration (current hardcoded order)."""
    return AIProviderConfig(
        providers=[
            ProviderConfigItem(id=pid, enabled=True, model=DEFAULT_MODELS.get(pid, ""))
            for pid in DEFAULT_ORDER
        ]
    )


def ordered_providers(config: AIProviderConfig) -> list[ProviderConfigItem]:
    """Order providers so the primary group (local or cloud) is tried first.

    Single source of truth for provider ordering — used by both chat/insights
    (``AIService``) and document extraction (``document_extractor``) so the two
    paths can never drift. ``primary_provider`` selects the group; within each
    group the original ``providers`` array order is preserved so manual
    reordering in Settings still applies.

    ``"auto"`` is resolved to a concrete group at call time by
    :func:`resolve_primary_provider` (which can check live key availability).
    When an unresolved ``"auto"`` reaches here (e.g. the sync default-config
    fallback), it is treated as local-first — the safe default that matches an
    Ollama-only box. ``AIService._get_provider_config`` upgrades it to cloud-first
    before any plan is built when a cloud key is present.
    """
    local = [p for p in config.providers if p.id == "ollama"]
    cloud = [p for p in config.providers if p.id != "ollama"]
    if config.primary_provider == "cloud":
        return cloud + local
    return local + cloud  # "local" or unresolved "auto"


async def resolve_primary_provider(config: AIProviderConfig) -> str:
    """Resolve ``primary_provider`` to a concrete group using live key availability.

    ``"auto"`` → ``"cloud"`` when any cloud provider is configured (key or Gemini
    ADC), otherwise ``"local"``. ``"cloud"``/``"local"`` pass through unchanged.
    Used by :meth:`AIService._get_provider_config` so every downstream caller
    (extraction + chat/insights) builds plans from the resolved order.
    """
    if config.primary_provider == "auto":
        from app.core.provider_keys import any_cloud_provider_configured

        return "cloud" if await any_cloud_provider_configured() else "local"
    return config.primary_provider
