"""Schemas for instance-wide AI provider key management (admin only)."""
from pydantic import BaseModel, Field

# Provider ids that may have a managed credential.
PROVIDER_IDS: tuple[str, ...] = ("openai", "gemini", "groq", "openrouter", "ollama")


class ProviderKeyStatus(BaseModel):
    """Masked status of one provider's credential.

    Never exposes plaintext: ``masked`` shows at most the last 4 characters
    (for secrets) or the full value (for the Ollama URL, which is not secret).
    """

    provider: str
    label: str
    is_set: bool  # True if a value is stored in the DB
    using_env: bool  # True if the effective value comes from the .env fallback
    masked: str | None
    is_secret: bool  # False for the Ollama URL


class ProviderKeysResponse(BaseModel):
    keys: list[ProviderKeyStatus]


class ProviderKeyUpdate(BaseModel):
    """Accepts plaintext; the server encrypts before storage."""

    provider: str = Field(..., pattern=r"^(openai|gemini|groq|openrouter|ollama)$")
    value: str = Field(..., min_length=1)


class ImportFromEnvResponse(BaseModel):
    imported: list[str]
    skipped: list[str]
