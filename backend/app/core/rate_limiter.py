"""Sliding window rate limiter with Redis backend."""
import time
from collections import defaultdict
from threading import Lock


class RateLimiter:
    """In-memory sliding window rate limiter with optional Redis backend."""

    def __init__(self, limit: int = 100, window_seconds: int = 60):
        """Initialize rate limiter with limit and window."""
        self.limit = limit
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)
        self.lock = Lock()

    def check_limit(self, key: str) -> tuple[bool, int]:
        """
        Check if request is allowed for given key (sync, in-memory only).

        Returns: (allowed, retry_after_seconds)
        """
        now = time.monotonic()
        window_start = now - self.window_seconds

        with self.lock:
            self.requests[key] = [ts for ts in self.requests[key] if ts > window_start]

            if len(self.requests[key]) < self.limit:
                self.requests[key].append(now)
                # Periodically prune stale keys to bound memory
                if len(self.requests) > 10_000:
                    stale = [k for k, v in self.requests.items() if not v]
                    for k in stale:
                        del self.requests[k]
                return (True, 0)

            oldest = self.requests[key][0]
            retry_after = int(oldest + self.window_seconds - now) + 1
            return (False, retry_after)

    async def check_limit_async(self, key: str) -> tuple[bool, int]:
        """
        Check rate limit using Redis sorted-set sliding window when available.

        Falls back to in-memory when Redis is unavailable.
        Returns: (allowed, retry_after_seconds)
        """
        from app.core.redis import get_redis

        redis = await get_redis()
        if redis is None:
            return self.check_limit(key)

        now = time.time()
        window_start = now - self.window_seconds
        member_key = f"rl:{key}"

        try:
            pipe = redis.pipeline()
            pipe.zremrangebyscore(member_key, "-inf", window_start)
            pipe.zcard(member_key)
            pipe.zadd(member_key, {str(now): now})
            pipe.expire(member_key, self.window_seconds + 1)
            results = await pipe.execute()

            count = results[1]
            if count < self.limit:
                return (True, 0)

            # Get oldest member for retry_after calculation
            oldest_entries = await redis.zrange(member_key, 0, 0, withscores=True)
            if oldest_entries:
                oldest_ts = oldest_entries[0][1]
                retry_after = int(oldest_ts + self.window_seconds - now) + 1
                return (False, max(1, retry_after))
            return (True, 0)
        except Exception:
            # Redis error — fall back to in-memory
            return self.check_limit(key)
