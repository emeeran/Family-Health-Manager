"""OpenAI API provider."""
import logging

from app.core.config import get_settings
from app.services.ai.base import get_cloud_client, retry_with_backoff

settings = get_settings()
logger = logging.getLogger(__name__)


PRIMARY_MODEL = "gpt-5.4-mini"
FALLBACK_MODEL = "gpt-5.4-nano"


async def call_openai_text(prompt: str, model: str | None = None) -> str | None:
    """Call OpenAI chat completions for text-based extraction.

    If model is specified, uses that single model.
    Otherwise tries PRIMARY_MODEL first, falls back to FALLBACK_MODEL on failure.
    """
    if not settings.OPENAI_API_KEY:
        return None
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    models_to_try = [model] if model else [PRIMARY_MODEL, FALLBACK_MODEL]

    for m in models_to_try:
        payload = {
            "model": m,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }

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
    b64_data: str, mime_type: str, extraction_prompt: str
) -> str | None:
    """Call OpenAI API for vision extraction."""
    if not settings.OPENAI_API_KEY:
        return None
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": PRIMARY_MODEL,
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
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    client = await get_cloud_client()
    resp = await client.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]
