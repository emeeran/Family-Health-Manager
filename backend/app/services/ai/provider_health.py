"""Pre-flight provider health probing for extraction (Phase 1 / A1).

A short-TTL cache of which providers are reachable, so confirmed-dead providers
can be pruned from the extraction chain *before* the sequential failover pays
the ``EXTRACTION_PROVIDER_TIMEOUT`` (15s) tax on each. With N dead cloud keys a
single extraction previously burned N×15s before reaching a live provider; the
batch path repeated that per file.

The cache is deliberately a **negative cache**: only providers positively
confirmed dead (within the TTL) are pruned. If no probe has run, the TTL has
expired, or a probe errored, nothing is pruned and the full configured chain
runs exactly as before. That makes this a pure no-op until a probe populates
the cache — so every existing unit test (which mocks providers and never calls
:func:`probe_providers`) keeps its current behaviour and stays green.

Probes are populated by:

* :func:`probe_providers` — called as a pre-flight at the start of the extract
  stream / batch-stream endpoints, and reusable anywhere.
* ``GET /ai/status`` — shares :func:`probe_one`, so opening the AI Status panel
  warms the cache for the next extraction.

The probe mirrors the proven ``/ai/status`` logic: Ollama is checked via the
instant ``/api/tags`` endpoint (never triggers a model load), cloud providers
get a tiny ``"Reply with only the word OK."`` prompt with a hard per-provider
timeout.
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

# How long a probe result is trusted. Short enough that a just-fixed key is
# retried soon, long enough to amortise one parallel probe across a batch and
# repeated extractions.
PROBE_TTL = 60.0

# Tiny prompt — we only need a non-empty reply to confirm the key works and the
# model name resolves. Kept identical to /ai/status so behaviour matches.
_PROBE_PROMPT = "Reply with only the word OK."

# Cached probe result: {"result": {provider_id: bool} | None, "expires_at": float}.
# ``result`` is None when no probe has run / it has expired / the last probe
# threw — in all those cases ``known_dead_providers`` returns an empty set so the
# full chain is used (the safe default).
_state: dict[str, object] = {"result": None, "expires_at": 0.0}


def clear() -> None:
    """Drop the cached probe (mainly for tests)."""
    _state["result"] = None
    _state["expires_at"] = 0.0


def known_dead_providers() -> set[str]:
    """Return provider ids confirmed dead by a recent, unexpired probe.

    Empty when no probe has run, the result has expired, or the cache holds no
    result (e.g. last probe raised). Callers MUST treat empty as "prune
    nothing" — never as "all dead".
    """
    result = _state["result"]
    if not isinstance(result, dict):
        return set()
    if time.monotonic() > float(_state["expires_at"]):
        return set()
    return {pid for pid, alive in result.items() if not alive}


def is_known_dead(provider_id: str) -> bool:
    """True only if a recent probe confirmed *provider_id* unreachable."""
    return provider_id in known_dead_providers()


async def probe_one(prov) -> dict:
    """Probe a single ``ProviderConfigItem``; return a status dict.

    The shape matches the historical ``/ai/status`` per-provider dict
    (``name``, ``id``, ``model``, ``available``, optional ``response_ms`` /
    ``error``) so the status endpoint can reuse this verbatim. Raises nothing —
    failures are reported via ``available=False`` + ``error``.
    """
    from app.schemas.ai_provider_config import PROVIDER_LABELS

    label = PROVIDER_LABELS.get(prov.id, prov.id)
    model = prov.model
    start = time.monotonic()

    if prov.id == "ollama":
        from app.core.config import get_settings
        from app.core.ollama_service import ollama_status
        from app.core.provider_keys import resolve_provider_value

        base_url = await resolve_provider_value("ollama")
        use_model = model or get_settings().OLLAMA_TEXT_MODEL
        if not base_url:
            return {"name": label, "id": prov.id, "model": use_model, "available": False,
                    "error": "No Ollama URL configured"}
        reachable, present = await ollama_status(use_model, base_url)
        if not reachable:
            return {"name": label, "id": prov.id, "model": use_model, "available": False,
                    "response_ms": round((time.monotonic() - start) * 1000),
                    "error": "Connection refused — is Ollama running?"}
        if not present:
            return {"name": label, "id": prov.id, "model": use_model, "available": False,
                    "response_ms": round((time.monotonic() - start) * 1000),
                    "error": f"Model '{use_model}' not installed"}
        return {"name": label, "id": prov.id, "model": use_model, "available": True,
                "response_ms": round((time.monotonic() - start) * 1000)}

    # Cloud providers: tiny test prompt. Configured-check first so an unset key
    # is reported instantly without a network round-trip.
    from app.core.provider_keys import is_provider_configured

    if not await is_provider_configured(prov.id):
        return {"name": label, "id": prov.id, "model": model, "available": False,
                "error": "No API key"}

    try:
        result: str | None = None
        if prov.id == "gemini":
            from app.services.ai.providers.gemini import call_gemini_text

            result = await call_gemini_text(_PROBE_PROMPT, model=model)
        elif prov.id == "openrouter":
            from app.services.ai.providers.openrouter import call_openrouter_text

            result = await call_openrouter_text(_PROBE_PROMPT, model=model)
        elif prov.id == "groq":
            from app.services.ai.providers.groq import call_groq_text

            result = await call_groq_text(_PROBE_PROMPT, model=model)
        elif prov.id == "openai":
            from app.services.ai.providers.openai import call_openai_text

            result = await call_openai_text(_PROBE_PROMPT, model=model)
        else:
            return {"name": label, "id": prov.id, "model": model, "available": False,
                    "error": "Unknown provider"}
        return {"name": label, "id": prov.id, "model": model, "available": bool(result),
                "response_ms": round((time.monotonic() - start) * 1000)}
    except Exception as exc:  # noqa: BLE001 — surface as unavailable, never raise
        return {"name": label, "id": prov.id, "model": model, "available": False,
                "response_ms": round((time.monotonic() - start) * 1000),
                "error": _friendly_error(exc)}


def _friendly_error(exc: Exception) -> str:
    """Translate provider HTTP errors into user-friendly messages."""
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        messages = {
            401: "Invalid API key",
            402: "Insufficient credits — top up your account",
            403: "API key lacks permission or API not enabled",
            404: "Model not found — check model name",
            429: "Rate limited — try again later",
        }
        return messages.get(status, f"HTTP {status}: {exc.response.text[:60]}")
    if isinstance(exc, httpx.TimeoutException):
        return "Request timed out"
    if isinstance(exc, httpx.ConnectError):
        return "Connection refused — is the service running?"
    return str(exc)[:100]


async def probe_providers(config, *, force: bool = False, timeout: float = 20.0) -> dict[str, bool]:
    """Probe every enabled provider in parallel; cache and return ``{id: alive}``.

    Wall-clock is the slowest single provider (≤ ``timeout``), not the sum.
    Results are cached for :data:`PROBE_TTL` seconds. ``force=True`` re-probes
    even with a fresh cache (used by /ai/status so the panel always reflects
    reality).

    The cache stores alive-booleans only (the rich per-provider dicts from
    :func:`probe_one` are returned to direct callers of the status endpoint via
    a separate path). A probe that itself raises is swallowed: the cache is left
    untouched (so a prior good result may still be trusted, and if there is
    none, ``known_dead_providers`` returns an empty set → full chain).
    """
    if not force:
        cached = _state["result"]
        if isinstance(cached, dict) and time.monotonic() <= float(_state["expires_at"]):
            return dict(cached)

    async def _check(prov) -> dict:
        try:
            return await asyncio.wait_for(probe_one(prov), timeout=timeout)
        except asyncio.TimeoutError:
            from app.schemas.ai_provider_config import PROVIDER_LABELS

            return {"id": prov.id, "name": PROVIDER_LABELS.get(prov.id, prov.id),
                    "model": prov.model, "available": False, "error": "Timed out"}
        except Exception as exc:  # noqa: BLE001
            from app.schemas.ai_provider_config import PROVIDER_LABELS

            return {"id": prov.id, "name": PROVIDER_LABELS.get(prov.id, prov.id),
                    "model": prov.model, "available": False, "error": _friendly_error(exc)}

    try:
        checked = await asyncio.gather(*(_check(p) for p in config.providers if p.enabled))
    except Exception:  # noqa: BLE001 — never let probing break the caller
        logger.warning("Provider probe raised; leaving health cache unchanged")
        return dict(_state["result"]) if isinstance(_state["result"], dict) else {}

    result = {c["id"]: bool(c.get("available")) for c in checked}
    _state["result"] = result
    _state["expires_at"] = time.monotonic() + PROBE_TTL
    return result


async def status_for_endpoint(config, *, timeout: float = 20.0) -> list[dict]:
    """Probe all providers and return the rich per-provider dicts for /ai/status.

    Also refreshes the negative cache used for pruning, so viewing the AI Status
    panel warms extraction's health knowledge as a side effect.
    """
    async def _check(prov) -> dict:
        try:
            return await asyncio.wait_for(probe_one(prov), timeout=timeout)
        except asyncio.TimeoutError:
            from app.schemas.ai_provider_config import PROVIDER_LABELS

            return {"id": prov.id, "name": PROVIDER_LABELS.get(prov.id, prov.id),
                    "model": prov.model, "available": False, "error": "Timed out"}
        except Exception as exc:  # noqa: BLE001
            from app.schemas.ai_provider_config import PROVIDER_LABELS

            return {"id": prov.id, "name": PROVIDER_LABELS.get(prov.id, prov.id),
                    "model": prov.model, "available": False, "error": _friendly_error(exc)}

    checked = await asyncio.gather(*(_check(p) for p in config.providers))
    # Refresh the negative cache from the same probe.
    _state["result"] = {c["id"]: bool(c.get("available")) for c in checked}
    _state["expires_at"] = time.monotonic() + PROBE_TTL
    return list(checked)
