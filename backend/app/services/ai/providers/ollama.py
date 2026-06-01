"""Ollama local AI provider — text, chat, streaming, and vision."""
import asyncio
import json
import logging
from collections.abc import AsyncGenerator

import httpx

from app.core.config import get_settings
from app.services.ai.base import get_ollama_client

settings = get_settings()
logger = logging.getLogger(__name__)


def _ollama_timeout(prompt_len: int) -> httpx.Timeout:
    """Adaptive timeout: shorter for small prompts, longer for complex ones."""
    read = min(30 + prompt_len // 500, 120)
    return httpx.Timeout(connect=10, read=read, write=10, pool=10)


async def _retry_request(fn, retries: int = 2, base_delay: float = 0.5):
    """Retry an httpx request with exponential backoff. Resets client on last failure."""
    for attempt in range(retries + 1):
        try:
            return await fn()
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            if attempt == retries:
                # Final failure — reset shared client
                from app.services.ai import base as _base
                if _base.ollama_client:
                    try:
                        await _base.ollama_client.aclose()
                    except Exception:
                        pass
                    _base.ollama_client = None
                raise
            delay = base_delay * (2 ** attempt)
            logger.debug("Ollama request failed (attempt %d/%d), retrying in %.1fs: %s",
                         attempt + 1, retries + 1, delay, exc)
            await asyncio.sleep(delay)


async def call_ollama_text(prompt: str) -> str | None:
    """Call local Ollama API for text generation — uses lighter model."""
    if not settings.OLLAMA_LOCAL_URL:
        return None
    url = f"{settings.OLLAMA_LOCAL_URL}/api/chat"
    payload = {
        "model": settings.OLLAMA_TEXT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_ctx": 16384, "num_predict": 2048, "temperature": 0.3},
    }
    timeout = _ollama_timeout(len(prompt))

    async def _do():
        client = await get_ollama_client()
        resp = await client.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    data = await _retry_request(_do)
    content = data.get("message", {}).get("content", "")
    if not content or not content.strip():
        logger.warning("Ollama text (%s) returned empty content", settings.OLLAMA_TEXT_MODEL)
        return None
    return content


async def ollama_chat(model: str, prompt: str) -> str | None:
    """Call local Ollama with a specific model."""
    if not settings.OLLAMA_LOCAL_URL:
        return None
    url = f"{settings.OLLAMA_LOCAL_URL}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_ctx": 32768, "num_predict": 4096, "temperature": 0.3},
    }
    timeout = _ollama_timeout(len(prompt))

    async def _do():
        client = await get_ollama_client()
        resp = await client.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    try:
        data = await _retry_request(_do)
        return data.get("message", {}).get("content")
    except Exception:
        raise


async def ollama_chat_stream(model: str, prompt: str) -> AsyncGenerator[str, None]:
    """Stream tokens from local Ollama model."""
    if not settings.OLLAMA_LOCAL_URL:
        return
    url = f"{settings.OLLAMA_LOCAL_URL}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "options": {"num_ctx": 32768, "num_predict": 4096, "temperature": 0.3},
    }
    client = await get_ollama_client()
    async with client.stream(
        "POST", url, json=payload,
        timeout=_ollama_timeout(len(prompt)),
    ) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.strip():
                continue
            try:
                chunk = json.loads(line)
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content
                if chunk.get("done"):
                    return
            except json.JSONDecodeError:
                continue


async def call_ollama_vision(
    b64_data: str, mime_type: str, extraction_prompt: str
) -> str | None:
    """Call local Ollama API for vision extraction."""
    if not settings.OLLAMA_LOCAL_URL:
        return None
    url = f"{settings.OLLAMA_LOCAL_URL}/api/chat"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [{
            "role": "user",
            "content": extraction_prompt,
            "images": [b64_data],
        }],
        "stream": False,
        "options": {"num_ctx": 8192, "num_predict": 4096, "temperature": 0.2},
    }
    try:
        client = await get_ollama_client()
        resp = await client.post(
            url, json=payload,
            timeout=_ollama_timeout(len(extraction_prompt)),
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content")
    except (httpx.TimeoutException, httpx.ConnectError):
        return None


async def call_ollama_ocr(
    b64_data: str, mime_type: str
) -> str | None:
    """Use local Ollama vision to OCR an image to text."""
    if not settings.OLLAMA_LOCAL_URL:
        return None
    ocr_prompt = (
        "Transcribe all the text in this document, including any handwritten text. "
        "Return ONLY the raw text, nothing else."
    )
    url = f"{settings.OLLAMA_LOCAL_URL}/api/chat"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [{
            "role": "user",
            "content": ocr_prompt,
            "images": [b64_data],
        }],
        "stream": False,  # type: ignore[dict-item]
        "options": {"num_ctx": 8192, "num_predict": 4096, "temperature": 0.1},
    }
    client = await get_ollama_client()
    resp = await client.post(
        url, json=payload,
        timeout=_ollama_timeout(len(ocr_prompt)),
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("message", {}).get("content")
