"""OpenRouter API provider."""

import logging

from app.core.config import get_settings
from app.core.provider_keys import resolve_provider_api_key
from app.services.ai.base import get_cloud_client, retry_with_backoff

settings = get_settings()
logger = logging.getLogger(__name__)


async def call_openrouter_text(prompt: str, model: str | None = None) -> str | None:
    """Call OpenRouter API for text-based generation."""
    api_key = await resolve_provider_api_key("openrouter")
    if not api_key:
        return None
    model = model or settings.OPENROUTER_TEXT_MODEL
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async def _do_call():
        client = await get_cloud_client()
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

    data = await retry_with_backoff(_do_call)
    return data["choices"][0]["message"]["content"]


async def call_openrouter_vision(
    b64_data: str, mime_type: str, extraction_prompt: str, model: str | None = None
) -> str | None:
    """Call OpenRouter API for vision extraction."""
    api_key = await resolve_provider_api_key("openrouter")
    if not api_key:
        return None
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": model or settings.OPENROUTER_VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": extraction_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{b64_data}",
                        },
                    },
                ],
            }
        ],
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    client = await get_cloud_client()
    resp = await client.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


async def call_openrouter_vision_multi(
    b64_images: list[str],
    mime_type: str,
    extraction_prompt: str,
    model: str | None = None,
) -> str | None:
    """Call OpenRouter vision with several page images in one request.

    Packs k images into one OpenAI-format ``content`` array. Free-tier vision
    models on OpenRouter vary in multi-image support; the caller falls back to
    per-page calls when this returns ``None``. Returns ``None`` for an empty list.
    """
    if not b64_images:
        return None
    api_key = await resolve_provider_api_key("openrouter")
    if not api_key:
        return None
    url = "https://openrouter.ai/api/v1/chat/completions"
    content: list = [{"type": "text", "text": extraction_prompt}]
    for b64 in b64_images:
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}}
        )
    payload = {
        "model": model or settings.OPENROUTER_VISION_MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.1,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    client = await get_cloud_client()
    resp = await client.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]
