"""Groq API provider."""

import logging

from app.core.provider_keys import resolve_provider_api_key
from app.services.ai.base import get_cloud_client, retry_with_backoff

logger = logging.getLogger(__name__)


async def call_groq_text(
    prompt: str,
    model: str = "llama-3.3-70b-versatile",
    max_tokens: int | None = None,
) -> str | None:
    """Call Groq API for text-based generation.

    ``max_tokens`` bounds the generated length when set (used by structured
    extraction to cap runaway output and trim latency/cost); omitted otherwise.
    """
    api_key = await resolve_provider_api_key("groq")
    if not api_key:
        return None
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
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


async def call_groq_vision(
    b64_data: str,
    mime_type: str,
    extraction_prompt: str,
    model: str | None = None,
    max_tokens: int | None = None,
) -> str | None:
    """Call Groq API for vision extraction."""
    api_key = await resolve_provider_api_key("groq")
    if not api_key:
        return None
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload: dict = {
        "model": model or "llama-3.3-70b-versatile",
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
    if max_tokens:
        payload["max_tokens"] = max_tokens
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    client = await get_cloud_client()
    resp = await client.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


async def call_groq_vision_multi(
    b64_images: list[str],
    mime_type: str,
    extraction_prompt: str,
    model: str | None = None,
    max_tokens: int | None = None,
) -> str | None:
    """Call Groq vision with several page images in one OpenAI-format request.

    Packs k images into one ``content`` array (the OpenAI chat schema Groq
    mirrors accepts multiple ``image_url`` entries), so a k-page batch is ONE
    call instead of k. Returns ``None`` for an empty list.
    """
    if not b64_images:
        return None
    api_key = await resolve_provider_api_key("groq")
    if not api_key:
        return None
    url = "https://api.groq.com/openai/v1/chat/completions"
    content: list = [{"type": "text", "text": extraction_prompt}]
    for b64 in b64_images:
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}}
        )
    payload: dict = {
        "model": model or "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.1,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    client = await get_cloud_client()
    resp = await client.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]
