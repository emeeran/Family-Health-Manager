"""Google Gemini AI provider."""

import json
import logging
import time
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.core.provider_keys import gemini_adc_file_path, resolve_provider_api_key
from app.services.ai.base import get_cloud_client, retry_with_backoff

settings = get_settings()
logger = logging.getLogger(__name__)

# Cached OAuth access token derived from Application Default Credentials. ADC
# user-credentials are refreshed via Google's OAuth endpoint; the resulting
# access token lives ~1h. Refreshed lazily ~60s before expiry.
_adc_cache: dict[str, object] = {"token": None, "expires_at": 0.0}


def _adc_access_token() -> str | None:
    """OAuth Bearer access token from Gemini ADC, cached until near expiry.

    Reads the ADC file (:func:`gemini_adc_file_path`), refreshes the token via
    Google's OAuth2 endpoint, and caches it. Returns ``None`` when no ADC file
    is configured, the file isn't an ``authorized_user`` credential, or the
    refresh fails — callers fall back to the API key. Synchronous (the refresh
    runs ~once per hour; the brief blocking call is acceptable).
    """
    now = time.time()
    cached = _adc_cache["token"]
    if cached and _adc_cache["expires_at"] > now + 60:
        return cached  # type: ignore[return-value]

    path = gemini_adc_file_path()
    if not path or not Path(path).is_file():
        return None
    try:
        adc = json.loads(Path(path).read_text())
        if adc.get("type") != "authorized_user":
            logger.warning(
                "Gemini ADC: only 'authorized_user' credentials are supported (got %s)",
                adc.get("type"),
            )
            return None
        resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": adc["client_id"],
                "client_secret": adc["client_secret"],
                "refresh_token": adc["refresh_token"],
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        token = payload["access_token"]
        _adc_cache["token"] = token
        _adc_cache["expires_at"] = now + int(payload.get("expires_in", 3600))
        return token
    except Exception as exc:
        logger.warning("Gemini ADC token refresh failed: %s", exc)
        return None


async def _gemini_auth_headers() -> dict[str, str] | None:
    """Auth headers for a Gemini request.

    Prefers Application Default Credentials (OAuth ``Bearer`` token); falls back
    to the API key (``x-goog-api-key``). Returns ``None`` when neither is
    available so callers can treat the provider as unconfigured.
    """
    token = _adc_access_token()
    if token:
        return {"Authorization": f"Bearer {token}"}
    api_key = await resolve_provider_api_key("gemini")
    if api_key:
        return {"x-goog-api-key": api_key}
    return None


async def call_gemini_text(prompt: str, model: str | None = None) -> str | None:
    """Call Google Gemini for text-based generation."""
    headers = await _gemini_auth_headers()
    if not headers:
        return None
    model = model or settings.GEMINI_TEXT_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1},
    }

    async def _do_call():
        client = await get_cloud_client()
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

    data = await retry_with_backoff(_do_call)
    return data["candidates"][0]["content"]["parts"][0]["text"]


async def call_gemini_vision(b64_data: str, mime_type: str, extraction_prompt: str) -> str | None:
    """Call Google Gemini API for vision extraction."""
    headers = await _gemini_auth_headers()
    if not headers:
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
    resp = await client.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


async def call_gemini_ocr(b64_data: str, mime_type: str) -> str | None:
    """Use Google Gemini to OCR an image to text."""
    headers = await _gemini_auth_headers()
    if not headers:
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
    resp = await client.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]
