"""Tests for rate limiting."""

import time
from unittest.mock import AsyncMock

import pytest

from app.api.rate_limit import RateLimiter
from app.core.config import Settings


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    return AsyncMock()


@pytest.fixture
def settings():
    """Create settings with rate limiting enabled."""
    return Settings(
        rate_limit_enabled=True,
        rate_limit_rps=10,
        rate_limit_burst=20,
    )


@pytest.mark.asyncio
async def test_rate_limit_allows_within_limit(mock_redis, settings):
    """Test that requests within limit are allowed."""
    rate_limiter = RateLimiter(mock_redis, settings)

    # Mock Redis operations
    mock_redis.zremrangebyscore.return_value = None
    mock_redis.zcard.return_value = 5  # Current count: 5
    mock_redis.zadd.return_value = 1
    mock_redis.expire.return_value = True

    allowed, info = await rate_limiter.check_rate_limit("test_identifier")

    assert allowed is True
    assert info["limit"] == 20  # burst limit
    assert info["remaining"] == 14  # 20 - 5 - 1
    mock_redis.zadd.assert_called_once()


@pytest.mark.asyncio
async def test_rate_limit_blocks_when_exceeded(mock_redis, settings):
    """Test that requests are blocked when rate limit is exceeded."""
    rate_limiter = RateLimiter(mock_redis, settings)

    # Mock Redis operations - burst limit reached
    mock_redis.zremrangebyscore.return_value = None
    mock_redis.zcard.return_value = 20  # Current count: 20 (at burst limit)
    mock_redis.zadd.return_value = 1
    mock_redis.expire.return_value = True

    allowed, info = await rate_limiter.check_rate_limit("test_identifier")

    assert allowed is False
    assert info["limit"] == 20
    assert info["remaining"] == 0
    assert "reset_at" in info
    # Should not add new request when limit exceeded
    mock_redis.zadd.assert_not_called()


@pytest.mark.asyncio
async def test_rate_limit_disabled(mock_redis):
    """Test that rate limiting is disabled when configured."""
    settings_disabled = Settings(rate_limit_enabled=False)
    rate_limiter = RateLimiter(mock_redis, settings_disabled)

    allowed, info = await rate_limiter.check_rate_limit("test_identifier")

    assert allowed is True
    # No Redis operations should be called when disabled
    mock_redis.zremrangebyscore.assert_not_called()
    mock_redis.zcard.assert_not_called()


@pytest.mark.asyncio
async def test_rate_limit_cleans_old_entries(mock_redis, settings):
    """Test that rate limiter removes old entries outside the window."""
    rate_limiter = RateLimiter(mock_redis, settings)

    mock_redis.zremrangebyscore.return_value = None
    mock_redis.zcard.return_value = 0
    mock_redis.zadd.return_value = 1
    mock_redis.expire.return_value = True

    current_time = time.time()
    await rate_limiter.check_rate_limit("test_identifier", window_seconds=1)

    # Should remove entries older than (current_time - 1)
    call_args = mock_redis.zremrangebyscore.call_args
    assert call_args[0][0] == "ratelimit:test_identifier"
    assert call_args[0][1] == 0
    # Score should be approximately current_time - 1 (with small delta)
    assert abs(call_args[0][2] - (current_time - 1)) < 0.1


@pytest.mark.asyncio
async def test_rate_limit_sets_expiry(mock_redis, settings):
    """Test that rate limiter sets TTL on the key."""
    rate_limiter = RateLimiter(mock_redis, settings)

    mock_redis.zremrangebyscore.return_value = None
    mock_redis.zcard.return_value = 0
    mock_redis.zadd.return_value = 1
    mock_redis.expire.return_value = True

    await rate_limiter.check_rate_limit("test_identifier", window_seconds=1)

    # Should set expiry to 2x window (for cleanup)
    mock_redis.expire.assert_called_once_with("ratelimit:test_identifier", 2)


@pytest.mark.asyncio
async def test_rate_limit_calculates_remaining_correctly(mock_redis, settings):
    """Test that remaining count is calculated correctly."""
    rate_limiter = RateLimiter(mock_redis, settings)

    mock_redis.zremrangebyscore.return_value = None
    mock_redis.zadd.return_value = 1
    mock_redis.expire.return_value = True

    test_cases = [
        (0, 19),  # 0 requests -> 19 remaining (20 - 0 - 1)
        (5, 14),  # 5 requests -> 14 remaining (20 - 5 - 1)
        (15, 4),  # 15 requests -> 4 remaining (20 - 15 - 1)
        (19, 0),  # 19 requests -> 0 remaining (20 - 19 - 1)
    ]

    for current_count, expected_remaining in test_cases:
        mock_redis.zcard.return_value = current_count
        allowed, info = await rate_limiter.check_rate_limit(f"identifier_{current_count}")
        assert allowed is True
        assert info["remaining"] == expected_remaining


@pytest.mark.asyncio
async def test_rate_limit_handles_redis_errors_gracefully(mock_redis, settings):
    """Test that rate limiter fails open on Redis errors."""
    rate_limiter = RateLimiter(mock_redis, settings)

    # Simulate Redis error
    mock_redis.zremrangebyscore.side_effect = Exception("Redis connection failed")

    allowed, info = await rate_limiter.check_rate_limit("test_identifier")

    # Should allow request on error (fail open)
    assert allowed is True
    assert info["limit"] == settings.rate_limit_rps


@pytest.mark.asyncio
async def test_rate_limit_uses_sliding_window(mock_redis, settings):
    """Test that rate limiter uses sliding window algorithm."""
    rate_limiter = RateLimiter(mock_redis, settings)

    mock_redis.zremrangebyscore.return_value = None
    mock_redis.zcard.return_value = 10
    mock_redis.zadd.return_value = 1
    mock_redis.expire.return_value = True

    current_time = time.time()
    window_seconds = 5

    await rate_limiter.check_rate_limit("test_identifier", window_seconds=window_seconds)

    # Verify that zremrangebyscore uses sliding window
    call_args = mock_redis.zremrangebyscore.call_args
    key = call_args[0][0]
    min_score = call_args[0][1]
    max_score = call_args[0][2]

    assert key == "ratelimit:test_identifier"
    assert min_score == 0
    # Max score should be current_time - window_seconds
    assert abs(max_score - (current_time - window_seconds)) < 0.1

    # Verify that zadd uses current timestamp as score
    zadd_call_args = mock_redis.zadd.call_args
    added_data = zadd_call_args[0][1]
    assert len(added_data) == 1
    timestamp_value = list(added_data.values())[0]
    assert abs(timestamp_value - current_time) < 0.1
