"""OpenRouter API provider."""
import logging

from app.core.config import get_settings
from app.services.ai.base import get_cloud_client, retry_with_backoff

settings = get_settings()
logger = logging.getLogger(__name__)


async def call_openrouter_text(prompt: str, model: str = "deepseek/deepseek-v4-flash") -> str | None:
    """Call OpenRouter API for text-based generation."""
    if not settings.OPENROUTER_API_KEY:
        return None
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
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
    if not settings.OPENROUTER_API_KEY:
        return None
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": "google/gemini-2.5-flash-preview:thinking",
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
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    client = await get_cloud_client()
    resp = await client.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]
