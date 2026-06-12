"""AI provider configuration schemas."""
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
    "groq": ["meta-llama/llama-4-scout-17b-16e-instruct", "llama-3.3-70b-versatile"],
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    "openai": ["gpt-5.4-mini", "gpt-5.4-nano", "gpt-4o", "gpt-4o-mini"],
}

DEFAULT_MODELS: dict[str, str] = {
    "ollama": settings.OLLAMA_TEXT_MODEL,
    "openrouter": "deepseek/deepseek-v4-flash",
    "groq": "meta-llama/llama-4-scout-17b-16e-instruct",
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-5.4-mini",
}

DEFAULT_ORDER: list[str] = ["ollama", "openrouter", "groq", "gemini", "openai"]


class ProviderConfigItem(BaseModel):
    """Configuration for a single AI provider."""

    id: str
    enabled: bool = True
    model: str = ""


class AIProviderConfig(BaseModel):
    """Ordered list of provider configurations. Array order = failover order."""

    providers: list[ProviderConfigItem]


class AIProviderConfigResponse(BaseModel):
    """Response including config plus static metadata for the frontend."""

    config: AIProviderConfig
    available_models: dict[str, list[str]]
    provider_labels: dict[str, str]


def default_provider_config() -> AIProviderConfig:
    """Return the default provider configuration (current hardcoded order)."""
    return AIProviderConfig(
        providers=[
            ProviderConfigItem(id=pid, enabled=True, model=DEFAULT_MODELS.get(pid, ""))
            for pid in DEFAULT_ORDER
        ]
    )
