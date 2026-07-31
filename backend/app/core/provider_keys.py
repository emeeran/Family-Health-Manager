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

import json
import logging
import os
import time
from pathlib import Path

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
SECRET_PROVIDERS: frozenset[str] = frozenset({"openai", "gemini", "groq", "openrouter"})

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


def normalize_ollama_url(value: str | None) -> str | None:
    """Ensure an Ollama base URL has an ``http(s)://`` scheme.

    The admin Settings UI stores whatever is typed. A scheme-less entry such as
    ``localhost:11434`` is a natural way to type the URL but makes httpx reject
    every Ollama request with "Request URL is missing an 'http://' or 'https://'
    protocol" — silently disabling the only working provider on a local
    (Ollama-only) install, so every extraction returns empty and the record form
    never auto-fills. Ollama serves plain HTTP on localhost, so a missing scheme
    defaults to ``http://``. Whitespace is trimmed.
    """
    if not value:
        return value
    url = value.strip()
    if not url:
        return url
    if "://" not in url:
        url = f"http://{url}"
    return url


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

    # Ollama is the only URL-type provider; tolerate scheme-less entry so a
    # stored value like "localhost:11434" does not silently break every Ollama
    # request with a missing-protocol error.
    if provider == "ollama":
        value = normalize_ollama_url(value)

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
    """True if the provider has a usable value (stored, or via the .env fallback).

    For Gemini, an Application Default Credentials file also counts as
    configured (see :func:`gemini_adc_configured`).
    """
    if await resolve_provider_value(provider):
        return True
    if provider == "gemini" and gemini_adc_configured():
        return True
    return False


def gemini_adc_file_path() -> str:
    """Resolved ADC file path for Gemini.

    Resolution order (Google's own ADC convention):

    1. explicit ``GEMINI_ADC_FILE`` setting
    2. ``GOOGLE_APPLICATION_CREDENTIALS`` env var
    3. the standard gcloud ADC location — ``$CLOUDSDK_CONFIG`` if set, else
       ``~/.config/gcloud/application_default_credentials.json``

    The gcloud fallback (3) lets ADC "just work" on any machine that has run
    ``gcloud auth application-default login`` with no extra configuration —
    important for the desktop app, which has no ``.env``. Callers gate on file
    existence (``is_file`` / :func:`gemini_adc_configured`), so returning a path
    that may not exist is safe.
    """
    settings = get_settings()
    if settings.GEMINI_ADC_FILE:
        return settings.GEMINI_ADC_FILE
    env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if env:
        return env
    cloudsdk = os.environ.get("CLOUDSDK_CONFIG", "")
    if cloudsdk:
        return os.path.join(cloudsdk, "application_default_credentials.json")
    return os.path.join(
        os.path.expanduser("~"), ".config", "gcloud", "application_default_credentials.json"
    )


def gemini_adc_configured() -> bool:
    """True if a readable Gemini ADC credentials file is configured."""
    path = gemini_adc_file_path()
    return bool(path) and Path(path).is_file()


_vertex_project_cache: dict[str, str | None] = {"resolved": False, "value": ""}


def gemini_vertex_project() -> str:
    """Vertex AI project used when routing Gemini through ADC.

    Returns the explicit ``VERTEX_PROJECT`` setting when set; otherwise infers it
    from the ADC file's ``quota_project_id`` — an ``authorized_user`` ADC from
    ``gcloud auth application-default login`` carries one, and that is the project
    Vertex bills against. Empty string when neither is available.

    Inference lets the desktop app (which has no ``.env`` / ``VERTEX_PROJECT``)
    reach Gemini via Vertex whenever a gcloud ADC file is present. The result is
    memoized (VERTEX_PROJECT + the ADC file are fixed for a process lifetime) so
    this stays off the per-call hot path.
    """
    if _vertex_project_cache["resolved"]:
        return _vertex_project_cache["value"] or ""
    _vertex_project_cache["resolved"] = True
    explicit = get_settings().VERTEX_PROJECT
    if explicit:
        _vertex_project_cache["value"] = explicit
        return explicit
    path = gemini_adc_file_path()
    if path and Path(path).is_file():
        try:
            data = json.loads(Path(path).read_text())
            qp = data.get("quota_project_id")
            if qp:
                _vertex_project_cache["value"] = str(qp)
                return str(qp)
        except (OSError, ValueError):
            pass
    _vertex_project_cache["value"] = ""
    return ""


async def any_cloud_provider_configured() -> bool:
    """True if any cloud (non-Ollama) provider has an API key configured."""
    for provider in ("openrouter", "gemini", "groq", "openai"):
        if await is_provider_configured(provider):
            return True
    return False
