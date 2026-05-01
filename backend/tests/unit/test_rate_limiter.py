"""Unit tests for rate limiter."""
import pytest
from unittest.mock import patch
from datetime import datetime, timedelta
from app.core.rate_limiter import RateLimiter


@pytest.fixture
def rate_limiter():
    """Create RateLimiter instance."""
    return RateLimiter(limit=5, window_seconds=60)


def test_check_limit_allows_under_limit(rate_limiter):
    """Test requests under limit are allowed."""
    for i in range(5):
        allowed, retry_after = rate_limiter.check_limit("test_key")
        assert allowed is True
        assert retry_after == 0


def test_check_limit_blocks_over_limit(rate_limiter):
    """Test requests over limit are blocked."""
    # Make 5 requests (at limit)
    for _ in range(5):
        allowed, _ = rate_limiter.check_limit("test_key")
        assert allowed is True

    # 6th request should be blocked
    allowed, retry_after = rate_limiter.check_limit("test_key")
    assert allowed is False
    assert retry_after > 0


def test_check_limit_different_keys(rate_limiter):
    """Test different keys have separate limits."""
    # Exhaust limit for key1
    for _ in range(5):
        rate_limiter.check_limit("key1")

    # key2 should still be allowed
    allowed, _ = rate_limiter.check_limit("key2")
    assert allowed is True


def test_check_limit_window_expires():
    """Test that old requests expire from window."""
    with patch("app.core.rate_limiter.datetime") as mock_datetime:
        limiter = RateLimiter(limit=2, window_seconds=60)

        # Set initial time
        initial_time = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = initial_time

        # Make 2 requests (at limit)
        limiter.check_limit("test_key")
        limiter.check_limit("test_key")

        # 3rd request should be blocked
        allowed, _ = limiter.check_limit("test_key")
        assert allowed is False

        # Advance time past window
        mock_datetime.now.return_value = initial_time + timedelta(seconds=61)

        # Should be allowed again
        allowed, _ = limiter.check_limit("test_key")
        assert allowed is True


def test_retry_after_calculation():
    """Test retry after is calculated correctly."""
    with patch("app.core.rate_limiter.datetime") as mock_datetime:
        limiter = RateLimiter(limit=1, window_seconds=60)

        initial_time = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = initial_time

        # Make 1 request (at limit)
        limiter.check_limit("test_key")

        # Advance time by 30 seconds
        mock_datetime.now.return_value = initial_time + timedelta(seconds=30)

        # Should be blocked with ~30 second retry
        allowed, retry_after = limiter.check_limit("test_key")
        assert allowed is False
        assert 29 <= retry_after <= 31
