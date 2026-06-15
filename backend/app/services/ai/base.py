"""Shared httpx clients, cache, lock management, and circuit breaker for AI service."""
import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from collections.abc import AsyncGenerator

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Circuit breaker — per-provider failure tracking
# ---------------------------------------------------------------------------
# Tracks consecutive failures per provider.  After MAX_FAILURES consecutive
# failures the circuit opens and the provider is skipped for COOLDOWN_SECONDS.
# Once the cooldown expires the circuit enters half-open state, allowing one
# probe request.  A successful call resets the failure count and closes the
# circuit; a failed probe re-opens it for another cooldown period.
#
# Performance optimization: avoids wasting time and resources on providers
# that are known to be down, reducing tail latency on failover chains.
# ---------------------------------------------------------------------------

_MAX_FAILURES = 3
_COOLDOWN_SECONDS = 60.0

# {provider_name: {"failures": int, "opened_at": float | None}}
_circuit_state: dict[str, dict] = {}


def record_provider_success(provider_name: str) -> None:
    """Reset failure count and close the circuit for *provider_name*."""
    _circuit_state.pop(provider_name, None)


def record_provider_failure(provider_name: str) -> None:
    """Increment failure count; open circuit when threshold is reached."""
    entry = _circuit_state.setdefault(provider_name, {"failures": 0, "opened_at": None})
    entry["failures"] += 1
    if entry["failures"] >= _MAX_FAILURES:
        entry["opened_at"] = time.monotonic()
        logger.info(
            "Circuit OPEN for provider %s after %d failures (cooldown %ds)",
            provider_name, entry["failures"], int(_COOLDOWN_SECONDS),
        )


def is_provider_available(provider_name: str) -> bool:
    """Return True if the provider's circuit is closed or half-open (cooldown expired).

    In half-open state the provider is given one chance to succeed; a subsequent
    failure will immediately re-open the circuit.
    """
    entry = _circuit_state.get(provider_name)
    if entry is None:
        return True
    if entry["opened_at"] is None:
        return True
    elapsed = time.monotonic() - entry["opened_at"]
    if elapsed >= _COOLDOWN_SECONDS:
        logger.debug("Circuit HALF-OPEN for provider %s — allowing probe", provider_name)
        return True
    return False


# Proper LRU cache using OrderedDict — survives across per-request instances
# Values are (content, timestamp) tuples for TTL support
member_context_cache: OrderedDict[str, tuple[str, float]] = OrderedDict()
MAX_CACHE_SIZE = 64
CACHE_TTL_SECONDS = 600  # 10 minutes

# Performance: AI response cache — avoids re-calling providers for identical
# question+context combinations within a short TTL window.
# Key: hash of (normalized_question + member_context_ids)
# Value: (response_text, provider_label, timestamp)
_ai_response_cache: OrderedDict[str, tuple[str, str, float]] = OrderedDict()
AI_RESPONSE_MAX_CACHE_SIZE = 50
AI_RESPONSE_CACHE_TTL = 1800  # 30 minutes

# Shared httpx clients for connection pooling — reused across all instances
cloud_client: httpx.AsyncClient | None = None
ollama_client: httpx.AsyncClient | None = None
_client_lock: asyncio.Lock | None = None

# Connection pool limits for httpx clients
_CLOUD_LIMITS = httpx.Limits(max_connections=50, max_keepalive_connections=20)
_OLLAMA_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)


def get_lock() -> asyncio.Lock:
    """Lazy lock to avoid binding to a closed event loop between tests."""
    global _client_lock
    if _client_lock is None:
        _client_lock = asyncio.Lock()
    return _client_lock


def exc_description(exc: BaseException) -> str:
    """Human-readable exception description that is never blank.

    httpx transport errors (e.g. ``ReadTimeout``, ``ConnectError``) stringify
    to an empty string, which makes log lines like ``"... failed: "`` useless.
    This always includes the exception type so failures stay diagnosable.
    """
    msg = str(exc).strip()
    return f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__


async def stream_with_heartbeat(
    chunk_agen: AsyncGenerator[str, None],
    *,
    interval: float = 15.0,
) -> AsyncGenerator[tuple[str, object], None]:
    """Yield model chunks while emitting periodic heartbeats during silent waits.

    Local CPU inference (e.g. medgemma) can spend minutes evaluating the prompt
    before the first token streams, leaving the SSE connection idle long enough
    for proxies/browsers to drop it. This races the chunk generator against a
    timer, yielding ``("beat", None)`` every ``interval`` seconds while waiting
    so callers can emit keep-alive events.

    Yields:
        ``("chunk", str)``  — a streamed token chunk from ``chunk_agen``
        ``("beat", None)``  — heartbeat (no model output yet)
        ``("error", exc)``  — the generator raised; caller should re-raise
        ``("done", None)``  — generator finished cleanly
    """
    queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

    async def _pump() -> None:
        try:
            async for c in chunk_agen:
                await queue.put(("chunk", c))
        except BaseException as exc:  # noqa: BLE001 — surface to caller
            await queue.put(("error", exc))
        else:
            await queue.put(("done", None))

    pump_task = asyncio.create_task(_pump())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=interval)
            except asyncio.TimeoutError:
                yield ("beat", None)
                continue
            yield item
            if item[0] in ("done", "error"):
                break
    finally:
        if not pump_task.done():
            pump_task.cancel()
        await asyncio.gather(pump_task, return_exceptions=True)


async def get_cloud_client() -> httpx.AsyncClient:
    """Get or create a shared httpx client for cloud AI providers."""
    global cloud_client
    async with get_lock():
        if cloud_client is None or cloud_client.is_closed:
            cloud_client = httpx.AsyncClient(timeout=60, limits=_CLOUD_LIMITS)
        return cloud_client


async def get_ollama_client() -> httpx.AsyncClient:
    """Get or create a shared httpx client for Ollama (longer timeout)."""
    global ollama_client
    async with get_lock():
        client = ollama_client
        if client is not None and not client.is_closed:
            # Detect dead event loop — client looks open but loop is gone
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                client = None
            else:
                if client._transport is None:
                    client = None
        if client is None or client.is_closed:
            ollama_client = httpx.AsyncClient(timeout=120, limits=_OLLAMA_LIMITS)
        return ollama_client


def invalidate_member_cache(member_id: "UUID | str") -> None:  # noqa: F821
    """Invalidate cached context for a member (call after record changes)."""
    key = str(member_id)
    member_context_cache.pop(key, None)


def put_cache(key: str, value: str) -> None:
    """Store value in LRU cache with TTL, evicting the least-recently-used entry."""
    if key in member_context_cache:
        member_context_cache.move_to_end(key)
    elif len(member_context_cache) >= MAX_CACHE_SIZE:
        member_context_cache.popitem(last=False)
    member_context_cache[key] = (value, time.monotonic())


def get_cache(key: str) -> str | None:
    """Retrieve value from LRU cache, promoting it as most-recently-used.

    Returns None if the key is missing or the entry has expired.
    """
    if key in member_context_cache:
        value, ts = member_context_cache[key]
        if time.monotonic() - ts > CACHE_TTL_SECONDS:
            member_context_cache.pop(key)
            return None
        member_context_cache.move_to_end(key)
        return value
    return None


# ---- Performance: AI response cache functions ----


def _ai_response_cache_key(question: str, member_context_ids: str) -> str:
    """Build a deterministic cache key from the normalized question and context IDs.

    Normalizes whitespace and casing so that trivially different phrasings
    of the same question hit the same cache entry.
    """
    normalized = " ".join(question.lower().split())
    raw = f"{normalized}:{member_context_ids}"
    return hashlib.sha256(raw.encode()).hexdigest()


def get_ai_response(question: str, member_context_ids: str) -> tuple[str, str] | None:
    """Look up a cached AI response for the given question + context.

    Returns (response_text, provider_label) on hit, or None on miss / expiry.
    """
    key = _ai_response_cache_key(question, member_context_ids)
    if key in _ai_response_cache:
        response, provider, ts = _ai_response_cache[key]
        if time.monotonic() - ts > AI_RESPONSE_CACHE_TTL:
            _ai_response_cache.pop(key)
            return None
        _ai_response_cache.move_to_end(key)
        logger.debug("AI response cache hit for question (provider=%s)", provider)
        return response, provider
    return None


def put_ai_response(
    question: str, member_context_ids: str, response: str, provider: str
) -> None:
    """Store an AI response in the response cache with LRU eviction."""
    key = _ai_response_cache_key(question, member_context_ids)
    if key in _ai_response_cache:
        _ai_response_cache.move_to_end(key)
    elif len(_ai_response_cache) >= AI_RESPONSE_MAX_CACHE_SIZE:
        _ai_response_cache.popitem(last=False)
    _ai_response_cache[key] = (response, provider, time.monotonic())


async def retry_with_backoff(
    fn,
    *args,
    max_retries: int = 2,
    base_delay: float = 1.0,
    retryable_statuses: tuple[int, ...] = (429, 502, 503, 504),
    **kwargs,
):
    """Retry an async call with exponential backoff on transient errors.

    Retries on httpx.HTTPStatusError with matching status codes.
    Respects Retry-After header on 429 responses.
    """
    import httpx

    last_exc: Exception = ValueError("No retries configured")  # type: ignore[assignment]
    for attempt in range(max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            status = exc.response.status_code
            if status not in retryable_statuses or attempt == max_retries:
                raise

            # Respect Retry-After header on 429
            delay = base_delay * (2 ** attempt)
            if status == 429:
                retry_after = exc.response.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        pass

            logger.warning(
                "Retryable error %d on attempt %d/%d, waiting %.1fs: %s",
                status, attempt + 1, max_retries + 1, delay, exc,
            )
            await asyncio.sleep(delay)
    raise last_exc
