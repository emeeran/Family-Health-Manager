"""Simple in-memory TTL cache with optional Redis backend."""
import json
import time
from threading import Lock


class TTLCache:
    """Thread-safe cache with time-to-live expiration and optional Redis backend."""

    def __init__(self, default_ttl: int = 300):
        self._store: dict[str, tuple[float, object]] = {}
        self._lock = Lock()
        self._default_ttl = default_ttl

    def get(self, key: str) -> object | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + (ttl or self._default_ttl), value)

    def invalidate(self, prefix: str = "") -> None:
        """Remove entries matching a key prefix (empty = clear all)."""
        with self._lock:
            if not prefix:
                self._store.clear()
            else:
                keys_to_remove = [k for k in self._store if k.startswith(prefix)]
                for k in keys_to_remove:
                    del self._store[k]

    async def get_async(self, key: str) -> object | None:
        """Get from Redis when available, falling back to in-memory."""
        from app.core.redis import get_redis

        redis = await get_redis()
        if redis is None:
            return self.get(key)

        try:
            raw = await redis.get(f"cache:{key}")
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            return self.get(key)

    async def set_async(self, key: str, value: object, ttl: int | None = None) -> None:
        """Set in Redis when available, falling back to in-memory."""
        from app.core.redis import get_redis

        redis = await get_redis()
        if redis is None:
            self.set(key, value, ttl)
            return

        try:
            await redis.set(
                f"cache:{key}",
                json.dumps(value, default=str),
                ex=ttl or self._default_ttl,
            )
        except Exception:
            self.set(key, value, ttl)

    async def invalidate_async(self, prefix: str = "") -> None:
        """Invalidate in Redis when available, falling back to in-memory."""
        from app.core.redis import get_redis

        redis = await get_redis()
        # Always invalidate in-memory too
        self.invalidate(prefix)

        if redis is None:
            return

        try:
            if not prefix:
                # Scan for all cache keys
                async for key in redis.scan_iter("cache:*"):
                    await redis.delete(key)
            else:
                async for key in redis.scan_iter(f"cache:{prefix}*"):
                    await redis.delete(key)
        except Exception:
            pass


# Shared cache instance — services can use this
cache = TTLCache(default_ttl=300)
