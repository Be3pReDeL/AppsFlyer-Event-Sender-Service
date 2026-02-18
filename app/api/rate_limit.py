"""Rate limiting middleware using Redis sliding window algorithm."""

import time
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.metrics import record_rate_limit_blocked

logger = get_logger(__name__)


class RateLimiter:
    """Redis-based rate limiter using sliding window algorithm."""

    def __init__(self, redis_client: aioredis.Redis, settings: Settings) -> None:
        self.redis = redis_client
        self.settings = settings
        self.enabled = settings.rate_limit_enabled
        self.rps = settings.rate_limit_rps
        self.burst = settings.rate_limit_burst

    async def check_rate_limit(
        self,
        identifier: str,
        window_seconds: int = 1,
    ) -> tuple[bool, dict[str, int]]:
        """Check if request is within rate limit using sliding window.

        Args:
            identifier: Unique identifier for rate limiting (token, IP, etc.)
            window_seconds: Time window in seconds

        Returns:
            Tuple of (allowed: bool, info: dict with remaining/limit)
        """
        if not self.enabled:
            return True, {"remaining": self.rps, "limit": self.rps}

        try:
            current_time = time.time()
            window_start = current_time - window_seconds
            key = f"ratelimit:{identifier}"

            # Use Redis sorted set with timestamp as score
            # Remove old entries outside the window
            await self.redis.zremrangebyscore(key, 0, window_start)

            # Count requests in current window
            count = await self.redis.zcard(key)

            if count >= self.burst:
                # Rate limit exceeded
                logger.warning(
                    "rate_limit_exceeded",
                    identifier=identifier,
                    count=count,
                    limit=self.burst,
                )
                return False, {
                    "remaining": 0,
                    "limit": self.burst,
                    "reset_at": int(current_time + window_seconds),
                }

            # Add current request
            await self.redis.zadd(key, {str(current_time): current_time})

            # Set expiry on key (cleanup)
            await self.redis.expire(key, window_seconds * 2)

            remaining = max(0, self.burst - count - 1)

            return True, {
                "remaining": remaining,
                "limit": self.burst,
                "reset_at": int(current_time + window_seconds),
            }

        except Exception as e:
            logger.error(
                "rate_limit_check_failed",
                identifier=identifier,
                error=str(e),
            )
            # On error, allow request (fail open)
            return True, {"remaining": self.rps, "limit": self.rps}


async def _get_redis(request: Request) -> aioredis.Redis:
    """Get Redis client from app state."""
    redis = request.app.state.redis
    if redis is None:
        # Rate limiting unavailable, but don't block requests
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable (Redis connection failed)",
        )
    return redis


async def check_rate_limit_dependency(
    request: Request,
    redis: Annotated[aioredis.Redis, Depends(_get_redis)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """FastAPI dependency for rate limiting.

    Raises:
        HTTPException: 429 if rate limit exceeded
    """
    if not settings.rate_limit_enabled:
        return

    rate_limiter = RateLimiter(redis, settings)

    # Determine identifier for rate limiting
    # Priority: token from auth > IP address
    identifier = None

    # Try to get token from query params (if available)
    token = request.query_params.get("token")
    if token:
        # Use hashed token to avoid storing plaintext
        import hashlib

        identifier = f"token:{hashlib.sha256(token.encode()).hexdigest()[:16]}"
    else:
        # Fallback to IP address
        client_ip = request.client.host if request.client else "unknown"
        identifier = f"ip:{client_ip}"

    allowed, info = await rate_limiter.check_rate_limit(identifier)

    if not allowed:
        # Determine identifier type for metrics
        identifier_type = "token" if identifier.startswith("token:") else "ip"
        record_rate_limit_blocked(identifier_type)

        logger.warning(
            "rate_limit_rejected",
            identifier=identifier,
            path=request.url.path,
            method=request.method,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Rate limit exceeded",
                "limit": info["limit"],
                "remaining": info["remaining"],
                "reset_at": info["reset_at"],
            },
            headers={
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": str(info["remaining"]),
                "X-RateLimit-Reset": str(info["reset_at"]),
                "Retry-After": str(info.get("reset_at", 0) - int(time.time())),
            },
        )

    # Add rate limit headers to response (will be added by middleware)
    request.state.rate_limit_info = info


def get_rate_limiter(redis: aioredis.Redis, settings: Settings) -> RateLimiter:
    """Factory function to create RateLimiter instance."""
    return RateLimiter(redis, settings)
