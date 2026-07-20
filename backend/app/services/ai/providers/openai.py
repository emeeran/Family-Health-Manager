"""OpenAI API provider."""

import logging

from app.core.provider_keys import resolve_provider_api_key
from app.services.ai.base import get_cloud_client, retry_with_backoff

logger = logging.getLogger(__name__)


PRIMARY_MODEL = "gpt-5.4-mini"
FALLBACK_MODEL = "gpt-5.4-nano"


async def call_openai_text(
    prompt: str, model: str | None = None, max_tokens: int | None = None
) -> str | None:
    """Call OpenAI chat completions for text-based extraction.

    If model is specified, uses that single model.
    Otherwise tries PRIMARY_MODEL first, falls back to FALLBACK_MODEL on failure.
    ``max_tokens`` bounds generation when set (structured extraction).
    """
    api_key = await resolve_provider_api_key("openai")
    if not api_key:
        return None
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    models_to_try = [model] if model else [PRIMARY_MODEL, FALLBACK_MODEL]

    for m in models_to_try:
        payload: dict = {
            "model": m,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async def _do_call():
            client = await get_cloud_client()
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

        try:
            data = await retry_with_backoff(_do_call)
            return data["choices"][0]["message"]["content"]
        except Exception:
            logger.warning("OpenAI %s failed, trying fallback", m)
            continue

    logger.error("All OpenAI models failed")
    return None


async def call_openai_vision(
    b64_data: str,
    mime_type: str,
    extraction_prompt: str,
    model: str | None = None,
    max_tokens: int | None = None,
) -> str | None:
    """Call OpenAI API for vision extraction."""
    api_key = await resolve_provider_api_key("openai")
    if not api_key:
        return None
    url = "https://api.openai.com/v1/chat/completions"
    payload: dict = {
        "model": model or PRIMARY_MODEL,
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


async def call_openai_vision_multi(
    b64_images: list[str],
    mime_type: str,
    extraction_prompt: str,
    model: str | None = None,
    max_tokens: int | None = None,
) -> str | None:
    """Call OpenAI vision with several page images in one request.

    Packs k images into one ``content`` array so a k-page batch is ONE call
    instead of k. Returns ``None`` for an empty list. Note OpenAI applies per-
    request image limits by tier; very large batches should be split upstream.
    """
    if not b64_images:
        return None
    api_key = await resolve_provider_api_key("openai")
    if not api_key:
        return None
    url = "https://api.openai.com/v1/chat/completions"
    content: list = [{"type": "text", "text": extraction_prompt}]
    for b64 in b64_images:
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}}
        )
    payload: dict = {
        "model": model or PRIMARY_MODEL,
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
