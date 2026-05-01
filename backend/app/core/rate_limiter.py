"""Sliding window rate limiter."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from threading import Lock


class RateLimiter:
    """In-memory sliding window rate limiter."""

    def __init__(self, limit: int = 100, window_seconds: int = 60):
        """Initialize rate limiter with limit and window."""
        self.limit = limit
        self.window = timedelta(seconds=window_seconds)
        self.requests: dict[str, list[datetime]] = defaultdict(list)
        self.lock = Lock()

    def check_limit(self, key: str) -> tuple[bool, int]:
        """
        Check if request is allowed for given key.

        Returns: (allowed, retry_after_seconds)
        """
        now = datetime.now(timezone.utc)
        window_start = now - self.window

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
            retry_after = int((oldest + self.window - now).total_seconds()) + 1
            return (False, retry_after)
