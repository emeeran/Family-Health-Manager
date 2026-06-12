"""Shared httpx clients, cache, and lock management for AI service."""
import asyncio
import logging
import time
from collections import OrderedDict

import httpx

logger = logging.getLogger(__name__)

# Proper LRU cache using OrderedDict — survives across per-request instances
# Values are (content, timestamp) tuples for TTL support
member_context_cache: OrderedDict[str, tuple[str, float]] = OrderedDict()
MAX_CACHE_SIZE = 64
CACHE_TTL_SECONDS = 600  # 10 minutes

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

    last_exc = None
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
