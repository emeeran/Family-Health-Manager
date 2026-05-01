"""Simple in-memory TTL cache for frequently-accessed data."""
import time
from threading import Lock


class TTLCache:
    """Thread-safe cache with time-to-live expiration."""

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

    def stats(self) -> tuple[int, int]:
        """Return (total_keys, expired_keys) for monitoring."""
        now = time.monotonic()
        with self._lock:
            total = len(self._store)
            expired = sum(1 for _, (exp, _) in self._store.items() if now > exp)
        return total, expired


# Shared cache instance — services can use this
cache = TTLCache(default_ttl=300)
