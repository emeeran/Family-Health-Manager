"""Tests for the primary-provider (Cloud vs Local) configuration."""

from app.schemas.ai_provider_config import (
    AIProviderConfig,
    ProviderConfigItem,
    default_provider_config,
)
from app.services.ai import AIService


def _cfg(primary: str) -> AIProviderConfig:
    return AIProviderConfig(
        providers=[
            ProviderConfigItem(id="ollama", enabled=True, model="medgemma"),
            ProviderConfigItem(id="openrouter", enabled=True, model="x"),
            ProviderConfigItem(id="gemini", enabled=True, model="gemini-2.5-flash"),
            ProviderConfigItem(id="openai", enabled=True, model="gpt"),
        ],
        primary_provider=primary,  # type: ignore[arg-type]
    )


def test_default_primary_provider_is_auto():
    """New configs default to 'auto' (cloud-first when a key exists, else local).

    See C1: a freshly-keyed household becomes cloud-first (30-60x faster) with
    no manual Settings change; an Ollama-only box stays local-first.
    """
    assert default_provider_config().primary_provider == "auto"


def test_primary_provider_accepts_cloud():
    cfg = AIProviderConfig(providers=[], primary_provider="cloud")  # type: ignore[arg-type]
    assert cfg.primary_provider == "cloud"


def test_ordered_providers_local_first():
    ordered = AIService._ordered_providers(_cfg("local"))
    assert [p.id for p in ordered] == ["ollama", "openrouter", "gemini", "openai"]


def test_ordered_providers_cloud_first():
    ordered = AIService._ordered_providers(_cfg("cloud"))
    assert [p.id for p in ordered] == ["openrouter", "gemini", "openai", "ollama"]


def test_ordered_providers_preserves_intra_group_order():
    # gemini before openrouter in the array -> stays that way within the cloud group.
    cfg = AIProviderConfig(
        providers=[
            ProviderConfigItem(id="gemini", enabled=True, model=""),
            ProviderConfigItem(id="ollama", enabled=True, model=""),
            ProviderConfigItem(id="openrouter", enabled=True, model=""),
        ],
        primary_provider="cloud",  # type: ignore[arg-type]
    )
    assert [p.id for p in AIService._ordered_providers(cfg)] == [
        "gemini",
        "openrouter",
        "ollama",
    ]
