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
    b64_data: str, mime_type: str, extraction_prompt: str
) -> str | None:
    """Call OpenRouter API for vision extraction."""
    api_key = await resolve_provider_api_key("openrouter")
    if not api_key:
        return None
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": settings.OPENROUTER_VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": extraction_prompt},
                {"type": "image_url", "image_url": {
                    "url": f"data:{mime_type};base64,{b64_data}",
                }},
            ],
        }],
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
