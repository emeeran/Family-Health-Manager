"""Fetch available models from each AI provider's API."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

from app.core.provider_keys import resolve_provider_api_key, resolve_provider_value

logger = logging.getLogger(__name__)


async def _fetch_openai(client: httpx.AsyncClient) -> list[str]:
    """Fetch model list from OpenAI."""
    api_key = await resolve_provider_api_key("openai")
    if not api_key:
        return []
    resp = await client.get(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    resp.raise_for_status()
    return sorted(m["id"] for m in resp.json().get("data", []))


async def _fetch_groq(client: httpx.AsyncClient) -> list[str]:
    """Fetch model list from Groq."""
    api_key = await resolve_provider_api_key("groq")
    if not api_key:
        return []
    resp = await client.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    resp.raise_for_status()
    return sorted(m["id"] for m in resp.json().get("data", []))


async def _fetch_openrouter(client: httpx.AsyncClient) -> list[str]:
    """Fetch model list from OpenRouter."""
    api_key = await resolve_provider_api_key("openrouter")
    if not api_key:
        return []
    resp = await client.get(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    resp.raise_for_status()
    return sorted(m["id"] for m in resp.json().get("data", []))


async def _fetch_gemini(client: httpx.AsyncClient) -> list[str]:
    """Fetch model list from Google Gemini."""
    api_key = await resolve_provider_api_key("gemini")
    if not api_key:
        return []
    resp = await client.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        headers={"x-goog-api-key": api_key},
    )
    resp.raise_for_status()
    models = []
    for m in resp.json().get("models", []):
        name = m.get("name", "")
        # Strip "models/" prefix returned by the API
        if name.startswith("models/"):
            name = name[len("models/") :]
        if name:
            models.append(name)
    return sorted(models)


async def _fetch_ollama(client: httpx.AsyncClient) -> list[str]:
    """Fetch locally available models from Ollama."""
    base_url = await resolve_provider_value("ollama")
    if not base_url:
        return []
    try:
        resp = await client.get(f"{base_url}/api/tags")
        resp.raise_for_status()
        return sorted(m["name"] for m in resp.json().get("models", []))
    except Exception as exc:
        # Ollama may not be running or misconfigured — return empty list, but
        # leave a debug trace so a silent empty model list is diagnosable.
        logger.debug("Ollama model fetch failed: %s", exc)
        return []


PROVIDER_FETCHERS: dict[str, Callable[[httpx.AsyncClient], Awaitable[list[str]]]] = {
    "openai": _fetch_openai,
    "groq": _fetch_groq,
    "openrouter": _fetch_openrouter,
    "gemini": _fetch_gemini,
    "ollama": _fetch_ollama,
}


async def fetch_available_models(provider: str | None = None) -> dict[str, list[str]]:
    """Fetch available models from one or all providers.

    With ``provider`` set, only that provider is queried (returns a single-key
    dict); unknown providers return an empty list for that key. Without it, all
    providers are fetched in parallel. Providers without API keys or that fail
    return an empty list.
    """
    if provider is not None:
        fetcher = PROVIDER_FETCHERS.get(provider)
        if fetcher is None:
            return {provider: []}
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                result = await fetcher(client)
            except Exception as exc:
                logger.warning("Failed to fetch models for %s: %s", provider, exc)
                result = []
        logger.debug("Fetched %d models for %s", len(result), provider)
        return {provider: result}

    async with httpx.AsyncClient(timeout=10) as client:
        tasks = {
            pid: asyncio.create_task(fetcher(client)) for pid, fetcher in PROVIDER_FETCHERS.items()
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    output: dict[str, list[str]] = {}
    for (pid, _task), result in zip(tasks.items(), results):
        if isinstance(result, Exception):
            logger.warning("Failed to fetch models for %s: %s", pid, result)
            output[pid] = []
        else:
            output[pid] = result
            logger.debug("Fetched %d models for %s", len(result), pid)

    return output
