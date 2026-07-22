"""Ollama local AI provider — text, chat, streaming, and vision."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

import httpx

from app.core.config import get_settings
from app.core.provider_keys import resolve_provider_value
from app.services.ai.base import get_ollama_client

settings = get_settings()
logger = logging.getLogger(__name__)


def _ollama_timeout(prompt_len: int, streaming: bool = False) -> httpx.Timeout:
    """Adaptive timeout: shorter for small prompts, longer for complex ones.

    ``streaming=True`` uses a generous read timeout sized to the prompt so
    CPU-only inference has headroom for model load + prompt evaluation that
    must complete before the first token streams. Measured CPU prompt-eval on
    medgemma is ~19.5 tok/s (~1 token per 2.2 chars), i.e. roughly 1 second
    per 43 prompt chars, so ``prompt_len // 40`` leaves margin. Once tokens
    flow, inter-chunk reads are fast — the read timeout only gates
    time-to-first-token, so a large cap is safe.
    """
    if streaming:
        read = min(settings.OLLAMA_TIMEOUT + prompt_len // 40, 1800)
    else:
        # Non-streaming returns the FULL response at once, so the read timeout
        # must cover CPU prompt eval (~prompt_len/40 s — the same per-char rate
        # as the streaming branch) PLUS generation (~100 s for a 2048-token
        # extraction). The old prompt_len//500 scaling was ~12x too small, so
        # CPU-only extractions timed out mid prompt-eval and surfaced as empty
        # provider failures ("All text providers failed").
        read = min(120 + prompt_len // 40, 900)
    return httpx.Timeout(connect=10, read=read, write=10, pool=10)


async def _reset_ollama_client() -> None:
    """Close and clear the shared Ollama client so the next call rebuilds it.

    Used after a terminal transport failure to discard a possibly-dead
    connection (mirrors the reset embedded in :func:`_retry_request`).
    """
    from app.services.ai import base as _base

    if _base.ollama_client:
        try:
            await _base.ollama_client.aclose()
        except Exception:
            pass
        _base.ollama_client = None


async def _retry_request(fn, retries: int = 2, base_delay: float = 0.5):
    """Retry an httpx request with exponential backoff. Resets client on last failure."""
    for attempt in range(retries + 1):
        try:
            return await fn()
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            if attempt == retries:
                # Final failure — reset shared client
                await _reset_ollama_client()
                raise
            delay = base_delay * (2**attempt)
            logger.debug(
                "Ollama request failed (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                retries + 1,
                delay,
                exc,
            )
            await asyncio.sleep(delay)


def _ollama_options(**opts: int | float) -> dict:
    """Build an Ollama ``options`` dict, injecting ``num_thread`` when set.

    Centralized so the CPU-thread pinning (``OLLAMA_NUM_THREAD``) is applied to
    every payload — it was previously omitted from all of them, leaving Ollama
    to default to physical cores and underuse SMT on this 6C/12T CPU.
    """
    if settings.OLLAMA_NUM_THREAD:
        opts["num_thread"] = settings.OLLAMA_NUM_THREAD
    return opts


def _think_suppressed(content: str) -> tuple[str, bool]:
    """Conditionally mark insight/chat content for qwen3 reasoning suppression.

    qwen3 is a "thinking" model: on CPU its ``<think>`` block is slow (enough to
    blow past proxy SSE timeouts on a Smart Report) and the tags leak into the
    streamed JSON/prose and corrupt parsing. Mirrors the extraction path, which
    always suppresses reasoning for structured output. Returns ``(content,
    suppress)``: callers append ``/no_think`` to the prompt and set ``think:
    False`` on the payload when ``suppress`` is True. Gated by
    ``OLLAMA_SUPPRESS_THINK`` so it's reversible without a rebuild.
    """
    if settings.OLLAMA_SUPPRESS_THINK:
        return f"{content}\n/no_think", True
    return content, False


async def call_ollama_text(
    prompt: str, model: str | None = None, fmt: str | None = None
) -> str | None:
    """Call local Ollama API for text generation — uses lighter model.

    ``fmt`` enables grammar-constrained output (e.g. ``"json"``); used for
    structured extraction to cut generation length and guarantee parseable JSON.
    """
    base_url = await resolve_provider_value("ollama")
    if not base_url:
        return None
    use_model = model or settings.OLLAMA_TEXT_MODEL
    # Structured (JSON) extraction: suppress qwen3 reasoning. Thinking is slow on
    # CPU and emits <think> tags that bloat the response; /no_think + think:false
    # give faster, cleaner JSON. (parse_extraction also strips any <think> that
    # slips through, so this is belt-and-suspenders.)
    if fmt:
        prompt = f"{prompt}\n/no_think"
    url = f"{base_url}/api/chat"
    payload = {
        "model": use_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": _ollama_options(num_ctx=16384, num_predict=2048, temperature=0.3),
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
    }
    if fmt:
        payload["format"] = fmt
        payload["think"] = False
    timeout = _ollama_timeout(len(prompt))

    async def _do():
        client = await get_ollama_client()
        resp = await client.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    data = await _retry_request(_do)
    content = data.get("message", {}).get("content", "")
    if not content or not content.strip():
        logger.warning("Ollama text (%s) returned empty content", use_model)
        return None
    return content


async def ollama_chat(model: str, prompt: str, num_predict: int = 4096) -> str | None:
    """Call local Ollama with a specific model."""
    base_url = await resolve_provider_value("ollama")
    if not base_url:
        return None
    content, suppress_think = _think_suppressed(prompt)
    url = f"{base_url}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "stream": False,
        "options": _ollama_options(num_ctx=32768, num_predict=num_predict, temperature=0.3),
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
    }
    if suppress_think:
        payload["think"] = False
    timeout = _ollama_timeout(len(content))

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


async def ollama_chat_stream(
    model: str, prompt: str, num_predict: int = 4096
) -> AsyncGenerator[str, None]:
    """Stream tokens from local Ollama model.

    Uses a generous read timeout so CPU-only inference has headroom to load the
    model and evaluate the prompt before the first token streams. Retries once
    on transient connection errors (``ConnectError``/``ReadError``) that occur
    before any output; a ``TimeoutException`` is surfaced directly, since a
    generous timeout that still fires means the model cannot keep up and
    retrying would only double the wait.
    """
    base_url = await resolve_provider_value("ollama")
    if not base_url:
        return
    content, suppress_think = _think_suppressed(prompt)
    url = f"{base_url}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "stream": True,
        "options": _ollama_options(num_ctx=32768, num_predict=num_predict, temperature=0.3),
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
    }
    if suppress_think:
        payload["think"] = False
    timeout = _ollama_timeout(len(content), streaming=True)

    produced = False
    for attempt in range(2):  # initial attempt + 1 retry on transient errors
        try:
            client = await get_ollama_client()
            async with client.stream("POST", url, json=payload, timeout=timeout) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        produced = True
                        yield content
                    if chunk.get("done"):
                        return
            return
        except httpx.TimeoutException:
            # Timeout already exhausted — retrying wastes another long wait.
            raise
        except (httpx.ConnectError, httpx.ReadError) as exc:
            if attempt == 1 or produced:
                # Final attempt, or partial output already streamed — do not
                # retry. Reset the shared client to clear a dead connection.
                await _reset_ollama_client()
                raise
            logger.debug("Ollama stream error (attempt 1/2), retrying: %s", exc)
            await asyncio.sleep(0.5)
            continue


async def call_ollama_vision(
    b64_data: str,
    mime_type: str,
    extraction_prompt: str,
    fmt: str | None = None,
    model: str | None = None,
) -> str | None:
    """Call local Ollama API for vision extraction.

    Uses the configured vision model (``OLLAMA_VISION_MODEL``, or ``model`` when
    passed in from the provider plan); returns ``None`` (skipped) when no vision
    model is set or it isn't pulled, so the provider chain falls through cleanly
    instead of feeding an image to a text-only model (the old behaviour with
    text-only ``qwen3``). ``fmt`` enables grammar-constrained output (e.g.
    ``"json"``) for extraction.
    """
    base_url = await resolve_provider_value("ollama")
    vision_model = model or settings.OLLAMA_VISION_MODEL
    if not base_url or not vision_model:
        return None
    if fmt:
        extraction_prompt = f"{extraction_prompt}\n/no_think"
    url = f"{base_url}/api/chat"
    payload = {
        "model": vision_model,
        "messages": [
            {
                "role": "user",
                "content": extraction_prompt,
                "images": [b64_data],
            }
        ],
        "stream": False,
        "options": _ollama_options(num_ctx=8192, num_predict=1024, temperature=0.2),
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
    }
    if fmt:
        payload["format"] = fmt
        payload["think"] = False
    try:
        client = await get_ollama_client()
        resp = await client.post(
            url,
            json=payload,
            timeout=_ollama_timeout(len(extraction_prompt)),
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content")
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError):
        # HTTPStatusError covers "model not found" (vision model not pulled).
        return None


async def call_ollama_vision_multi(
    b64_images: list[str],
    mime_type: str,
    extraction_prompt: str,
    fmt: str | None = None,
    model: str | None = None,
) -> str | None:
    """Call local Ollama vision with several page images in one request.

    Ollama's chat ``images`` field is a list, so multiple pages can be sent in a
    single generation. Requires a configured vision model (returns ``None``
    otherwise). Note Ollama serializes one generation per model, so a single
    multi-image call still beats k separate calls (k-1 fewer queue waits).
    """
    if not b64_images:
        return None
    base_url = await resolve_provider_value("ollama")
    vision_model = model or settings.OLLAMA_VISION_MODEL
    if not base_url or not vision_model:
        return None
    if fmt:
        extraction_prompt = f"{extraction_prompt}\n/no_think"
    url = f"{base_url}/api/chat"
    payload = {
        "model": vision_model,
        "messages": [{"role": "user", "content": extraction_prompt, "images": b64_images}],
        "stream": False,
        "options": _ollama_options(num_ctx=8192, num_predict=1024, temperature=0.2),
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
    }
    if fmt:
        payload["format"] = fmt
        payload["think"] = False
    try:
        client = await get_ollama_client()
        # Multi-image prompts are larger; let the adaptive timeout grow with it.
        resp = await client.post(
            url, json=payload, timeout=_ollama_timeout(len(extraction_prompt))
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content")
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError):
        return None


async def call_ollama_ocr(b64_data: str, mime_type: str) -> str | None:
    """Use local Ollama vision to OCR an image to text.

    Requires a configured vision model (``OLLAMA_VISION_MODEL``); returns ``None``
    when unset or not pulled.
    """
    base_url = await resolve_provider_value("ollama")
    if not base_url or not settings.OLLAMA_VISION_MODEL:
        return None
    ocr_prompt = (
        "Transcribe all the text in this document, including any handwritten text. "
        "Return ONLY the raw text, nothing else."
    )
    url = f"{base_url}/api/chat"
    payload = {
        "model": settings.OLLAMA_VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": ocr_prompt,
                "images": [b64_data],
            }
        ],
        "stream": False,  # type: ignore[dict-item]
        "options": _ollama_options(num_ctx=8192, num_predict=4096, temperature=0.1),
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
    }
    try:
        client = await get_ollama_client()
        resp = await client.post(
            url,
            json=payload,
            timeout=_ollama_timeout(len(ocr_prompt)),
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content")
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError):
        return None
