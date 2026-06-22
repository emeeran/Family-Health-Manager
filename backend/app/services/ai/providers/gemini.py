"""Google Gemini AI provider."""

import logging


from app.core.config import get_settings
from app.core.provider_keys import resolve_provider_api_key
from app.services.ai.base import get_cloud_client, retry_with_backoff

settings = get_settings()
logger = logging.getLogger(__name__)


async def call_gemini_text(prompt: str, model: str | None = None) -> str | None:
    """Call Google Gemini for text-based generation."""
    api_key = await resolve_provider_api_key("gemini")
    if not api_key:
        return None
    model = model or settings.GEMINI_TEXT_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1},
    }

    async def _do_call():
        client = await get_cloud_client()
        resp = await client.post(url, json=payload, headers={"x-goog-api-key": api_key})
        resp.raise_for_status()
        return resp.json()

    data = await retry_with_backoff(_do_call)
    return data["candidates"][0]["content"]["parts"][0]["text"]


async def call_gemini_vision(b64_data: str, mime_type: str, extraction_prompt: str) -> str | None:
    """Call Google Gemini API for vision extraction."""
    api_key = await resolve_provider_api_key("gemini")
    if not api_key:
        return None
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{settings.GEMINI_VISION_MODEL}:generateContent"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": extraction_prompt},
                    {"inline_data": {"mime_type": mime_type, "data": b64_data}},
                ]
            }
        ],
        "generationConfig": {"temperature": 0.1},
    }
    client = await get_cloud_client()
    resp = await client.post(url, json=payload, headers={"x-goog-api-key": api_key})
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


async def call_gemini_ocr(b64_data: str, mime_type: str) -> str | None:
    """Use Google Gemini to OCR an image to text."""
    api_key = await resolve_provider_api_key("gemini")
    if not api_key:
        return None
    ocr_prompt = (
        "Transcribe all the text in this document, including any handwritten text. "
        "Return ONLY the raw text, nothing else."
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{settings.GEMINI_VISION_MODEL}:generateContent"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": ocr_prompt},
                    {"inline_data": {"mime_type": mime_type, "data": b64_data}},
                ]
            }
        ],
        "generationConfig": {"temperature": 0.1},
    }
    client = await get_cloud_client()
    resp = await client.post(url, json=payload, headers={"x-goog-api-key": api_key})
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]
