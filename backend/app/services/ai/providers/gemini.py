"""Google Gemini AI provider.

Two auth paths, picked automatically:
- **Application Default Credentials → Vertex AI.** ADC user-credentials (from
  ``gcloud auth application-default login``) carry the ``cloud-platform`` scope,
  which Vertex AI accepts. The Generative Language API needs a ``generative-
  language`` scope that gcloud will *not* grant, so ADC only reaches Gemini via
  Vertex (project-scoped endpoints). Requires ``GEMINI_ADC_FILE`` +
  ``VERTEX_PROJECT``.
- **API key → Generative Language API.** The fallback when no ADC is set; uses
  the ``x-goog-api-key`` header against ``generativelanguage.googleapis.com``.
"""

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
    refresh fails. Synchronous (the refresh runs ~once per hour; the brief
    blocking call is acceptable).
    """
    now = time.time()
    cached = _adc_cache["token"]
    expires_at = _adc_cache["expires_at"]
    if cached and isinstance(expires_at, (int, float)) and expires_at > now + 60:
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


async def _gemini_generate(
    model: str,
    parts: list,
    temperature: float = 0.1,
    gemini_auth: str = "auto",
    max_output_tokens: int | None = None,
) -> str | None:
    """Call Gemini ``generateContent`` via Vertex AI (ADC) or Gen Lang API (key).

    ``parts`` is the Gemini ``parts`` list (e.g. ``[{"text": prompt}]`` or with
    an ``inline_data`` for vision). Returns the concatenated text response, or
    ``None`` when neither ADC nor an API key is available.

    ``gemini_auth`` overrides the automatic ADC-vs-key choice:

    * ``"auto"`` — ADC (Vertex) when a credentials file + ``VERTEX_PROJECT`` are
      configured, otherwise the API key (the original behaviour).
    * ``"adc"`` — force ADC; if it isn't configured, fall back to the API key
      with a warning rather than failing the whole provider chain.
    * ``"api_key"`` — skip ADC entirely and use the Generative Language API.

    ``max_output_tokens`` bounds generation when set (structured extraction).
    """
    generation_config: dict = {"temperature": temperature}
    if max_output_tokens:
        generation_config["maxOutputTokens"] = max_output_tokens
    payload = {
        # Vertex requires an explicit role on each content; the Gen Lang API
        # accepts it too, so it's included unconditionally.
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": generation_config,
    }

    token = _adc_access_token()
    adc_ready = bool(token and settings.VERTEX_PROJECT)

    if gemini_auth == "api_key":
        use_adc = False
    elif gemini_auth == "adc":
        if not adc_ready:
            logger.warning(
                "Gemini auth='adc' requested but ADC is not configured "
                "(no readable credentials file or VERTEX_PROJECT set); "
                "falling back to API key"
            )
        use_adc = adc_ready
    else:  # "auto"
        use_adc = adc_ready

    if use_adc:
        url = (
            f"https://{settings.VERTEX_LOCATION}-aiplatform.googleapis.com/v1/projects/"
            f"{settings.VERTEX_PROJECT}/locations/{settings.VERTEX_LOCATION}/"
            f"publishers/google/models/{model}:generateContent"
        )
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    else:
        api_key = await resolve_provider_api_key("gemini")
        if not api_key:
            return None
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    async def _do_call():
        client = await get_cloud_client()
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

    data = await retry_with_backoff(_do_call)
    return data["candidates"][0]["content"]["parts"][0]["text"]


async def call_gemini_text(
    prompt: str,
    model: str | None = None,
    gemini_auth: str = "auto",
    max_tokens: int | None = None,
) -> str | None:
    """Call Google Gemini for text-based generation."""
    return await _gemini_generate(
        model or settings.GEMINI_TEXT_MODEL,
        [{"text": prompt}],
        gemini_auth=gemini_auth,
        max_output_tokens=max_tokens,
    )


async def call_gemini_vision(
    b64_data: str,
    mime_type: str,
    extraction_prompt: str,
    model: str | None = None,
    gemini_auth: str = "auto",
    max_tokens: int | None = None,
) -> str | None:
    """Call Google Gemini API for vision extraction."""
    return await _gemini_generate(
        model or settings.GEMINI_VISION_MODEL,
        [
            {"text": extraction_prompt},
            {"inline_data": {"mime_type": mime_type, "data": b64_data}},
        ],
        gemini_auth=gemini_auth,
        max_output_tokens=max_tokens,
    )


async def call_gemini_vision_multi(
    b64_images: list[str],
    mime_type: str,
    extraction_prompt: str,
    model: str | None = None,
    gemini_auth: str = "auto",
    max_tokens: int | None = None,
) -> str | None:
    """Call Gemini with several page images in one request (multi-page scan).

    Gemini's ``parts`` list accepts any number of ``inline_data`` images, so a
    k-page batch becomes ONE call instead of k. Returns ``None`` for an empty
    list (caller should fall back to single-image).
    """
    if not b64_images:
        return None
    parts: list = [{"text": extraction_prompt}]
    for b64 in b64_images:
        parts.append({"inline_data": {"mime_type": mime_type, "data": b64}})
    return await _gemini_generate(
        model or settings.GEMINI_VISION_MODEL,
        parts,
        gemini_auth=gemini_auth,
        max_output_tokens=max_tokens,
    )


async def call_gemini_ocr(
    b64_data: str, mime_type: str, model: str | None = None, gemini_auth: str = "auto"
) -> str | None:
    """Use Google Gemini to OCR an image to text."""
    ocr_prompt = (
        "Transcribe all the text in this document, including any handwritten text. "
        "Return ONLY the raw text, nothing else."
    )
    return await _gemini_generate(
        model or settings.GEMINI_VISION_MODEL,
        [
            {"text": ocr_prompt},
            {"inline_data": {"mime_type": mime_type, "data": b64_data}},
        ],
        gemini_auth=gemini_auth,
    )
