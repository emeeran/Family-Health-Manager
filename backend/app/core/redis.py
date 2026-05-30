"""Redis connection singleton.

Returns None when REDIS_URL is empty (dev mode), allowing graceful
fallback to in-memory implementations.
"""
import logging
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_redis = None


async def get_redis():
    """Get or create the shared Redis connection pool."""
    global _redis
    if _redis is not None:
        return _redis

    settings = get_settings()
    if not settings.REDIS_URL:
        return None

    try:
        import redis.asyncio as aioredis

        _redis = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=10,
        )
        # Verify connection
        await _redis.ping()
        logger.info("Redis connected: %s", settings.REDIS_URL)
        return _redis
    except Exception:
        logger.warning("Redis connection failed — falling back to in-memory")
        _redis = None
        return None


async def close_redis():
    """Close the Redis connection pool on shutdown."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
        logger.info("Redis connection closed")
