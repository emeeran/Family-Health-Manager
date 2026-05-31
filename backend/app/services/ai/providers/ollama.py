"""Ollama local AI provider — text, chat, streaming, and vision."""
import json
import logging
from collections.abc import AsyncGenerator

import httpx

from app.core.config import get_settings
from app.services.ai.base import get_ollama_client

settings = get_settings()
logger = logging.getLogger(__name__)


async def call_ollama_text(prompt: str) -> str | None:
    """Call local Ollama API for text generation — uses lighter model."""
    if not settings.OLLAMA_LOCAL_URL:
        return None
    url = f"{settings.OLLAMA_LOCAL_URL}/api/chat"
    payload = {
        "model": settings.OLLAMA_TEXT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_ctx": 8192},
    }
    client = await get_ollama_client()
    resp = await client.post(url, json=payload)
    resp.raise_for_status()
    data = resp.json()
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
    }
    try:
        client = await get_ollama_client()
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content")
    except Exception:
        # Reset shared client on failure — connection pool may be corrupted
        from app.services.ai import base as _base
        if _base.ollama_client:
            try:
                await _base.ollama_client.aclose()
            except Exception:
                pass
            _base.ollama_client = None
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
        "options": {"num_ctx": 32768},
    }
    client = await get_ollama_client()
    async with client.stream("POST", url, json=payload) as resp:
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
        "options": {"num_ctx": 8192},
    }
    try:
        client = await get_ollama_client()
        resp = await client.post(url, json=payload)
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
        "options": {"num_ctx": 8192},
    }
    client = await get_ollama_client()
    resp = await client.post(url, json=payload)
    resp.raise_for_status()
    data = resp.json()
    return data.get("message", {}).get("content")
