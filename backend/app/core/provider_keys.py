"""Resolve AI provider credentials (API keys / Ollama URL) at call time.

This is the single source of truth for "which value does provider X use right
now?" It prefers a value stored encrypted in the ``app_secrets`` table (set via
the admin Settings UI) and falls back to the matching ``.env``/``Settings``
field when no stored value exists. That keeps existing ``.env``-based
deployments working unchanged while making the UI the authoritative source once
a key is saved there.

The provider modules are ``async`` and read a module-level ``settings``
singleton with no DB session and no caller-passed key, so this resolver opens
its own short-lived session and memoises the result for a few seconds. Writes
(in the admin router) call :func:`invalidate_provider_cache` so changes take
effect immediately within the process; the TTL only bounds staleness across
separate worker processes.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.encryption import decrypt_secret
from app.models.app_secret import AppSecret

logger = logging.getLogger(__name__)

# Canonical secret name stored in app_secrets.key, keyed by provider id.
PROVIDER_SECRET_KEYS: dict[str, str] = {
    "openai": "openai_api_key",
    "gemini": "gemini_api_key",
    "groq": "groq_api_key",
    "openrouter": "openrouter_api_key",
    "ollama": "ollama_local_url",  # a URL, not a secret — managed identically
}

# Matching Settings (.env) attribute used as the cold-start fallback.
_SETTINGS_ATTR: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "ollama": "OLLAMA_LOCAL_URL",
}

# Providers whose stored value is a secret (masked everywhere); Ollama is a URL.
SECRET_PROVIDERS: frozenset[str] = frozenset(
    {"openai", "gemini", "groq", "openrouter"}
)

# Short so a just-saved key is picked up quickly even without explicit
# invalidation (e.g. from another worker process).
_CACHE_TTL = 5.0
# cache[secret_key] = (monotonic_timestamp, resolved_value_or_None)
_cache: dict[str, tuple[float, str | None]] = {}


async def _load_from_db(secret_key: str) -> str | None:
    """Decrypt and return the stored value for ``secret_key``, or ``None``."""
    async with SessionLocal() as db:
        row = (
            await db.execute(select(AppSecret.value).where(AppSecret.key == secret_key))
        ).scalar_one_or_none()
        return decrypt_secret(row) if row else None


def _fallback_from_env(provider: str) -> str | None:
    """The ``.env``/Settings value for ``provider``, or ``None`` when unset."""
    value = getattr(get_settings(), _SETTINGS_ATTR[provider], "")
    return value or None


def get_env_fallback(provider: str) -> str | None:
    """Public accessor for the ``.env``/Settings fallback value (or ``None``)."""
    return _fallback_from_env(provider)


async def resolve_provider_value(provider: str) -> str | None:
    """Return the effective value for ``provider``.

    Stored (DB) value wins; otherwise the ``.env`` fallback is used. Returns
    ``None`` when neither is set. Results are memoised for ``_CACHE_TTL``
    seconds per secret key.
    """
    secret_key = PROVIDER_SECRET_KEYS[provider]
    now = time.monotonic()

    cached = _cache.get(secret_key)
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]

    value: str | None
    try:
        value = await _load_from_db(secret_key)
    except Exception:
        # Never let a credential lookup break a user-facing request — fall back
        # to .env and log for investigation.
        logger.exception("Failed loading app_secret %s; using .env fallback", secret_key)
        value = None

    if not value:
        value = _fallback_from_env(provider)

    _cache[secret_key] = (now, value)
    return value


async def resolve_provider_api_key(provider: str) -> str | None:
    """Alias of :func:`resolve_provider_value` for the cloud API-key providers."""
    return await resolve_provider_value(provider)


def invalidate_provider_cache(provider: str | None = None) -> None:
    """Drop the cached value so the next read re-queries the database.

    Call after any write (PUT/DELETE/import) in the admin router. Pass a
    provider id to invalidate one key, or ``None`` to clear all.
    """
    if provider is None:
        _cache.clear()
    else:
        _cache.pop(PROVIDER_SECRET_KEYS.get(provider, ""), None)


async def is_provider_configured(provider: str) -> bool:
    """True if the provider has a usable value (stored, or via the .env fallback)."""
    return bool(await resolve_provider_value(provider))


async def any_cloud_provider_configured() -> bool:
    """True if any cloud (non-Ollama) provider has an API key configured."""
    for provider in ("openrouter", "gemini", "groq", "openai"):
        if await is_provider_configured(provider):
            return True
    return False
