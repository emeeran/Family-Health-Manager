"""Google Gemini AI provider."""
import logging


from app.core.config import get_settings
from app.services.ai.base import get_cloud_client, retry_with_backoff

settings = get_settings()
logger = logging.getLogger(__name__)


async def call_gemini_text(prompt: str, model: str = "gemini-2.5-flash") -> str | None:
    """Call Google Gemini for text-based generation."""
    if not settings.GEMINI_API_KEY:
        return None
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:generateContent"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1},
    }

    async def _do_call():
        client = await get_cloud_client()
        resp = await client.post(url, json=payload, headers={"x-goog-api-key": settings.GEMINI_API_KEY})
        resp.raise_for_status()
        return resp.json()

    data = await retry_with_backoff(_do_call)
    return data["candidates"][0]["content"]["parts"][0]["text"]


async def call_gemini_vision(
    b64_data: str, mime_type: str, extraction_prompt: str
) -> str | None:
    """Call Google Gemini API for vision extraction."""
    if not settings.GEMINI_API_KEY:
        return None
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        "models/gemini-2.5-flash:generateContent"
    )
    payload = {
        "contents": [{
            "parts": [
                {"text": extraction_prompt},
                {"inline_data": {"mime_type": mime_type, "data": b64_data}},
            ]
        }],
        "generationConfig": {"temperature": 0.1},
    }
    client = await get_cloud_client()
    resp = await client.post(url, json=payload, headers={"x-goog-api-key": settings.GEMINI_API_KEY})
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


async def call_gemini_ocr(
    b64_data: str, mime_type: str
) -> str | None:
    """Use Google Gemini to OCR an image to text."""
    if not settings.GEMINI_API_KEY:
        return None
    ocr_prompt = (
        "Transcribe all the text in this document, including any handwritten text. "
        "Return ONLY the raw text, nothing else."
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        "models/gemini-2.5-flash:generateContent"
    )
    payload = {
        "contents": [{
            "parts": [
                {"text": ocr_prompt},
                {"inline_data": {"mime_type": mime_type, "data": b64_data}},
            ]
        }],
        "generationConfig": {"temperature": 0.1},
    }
    client = await get_cloud_client()
    resp = await client.post(url, json=payload, headers={"x-goog-api-key": settings.GEMINI_API_KEY})
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]
