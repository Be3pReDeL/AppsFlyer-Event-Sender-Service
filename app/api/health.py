"""Health check endpoints for liveness and readiness probes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

router = APIRouter(tags=["Health"])
logger = get_logger(__name__)


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    service: str
    version: str


class ReadinessResponse(BaseModel):
    """Readiness check response model."""

    status: str
    service: str
    version: str
    checks: dict[str, bool]


@router.get(
    "/health/live",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns OK if the service is alive and running.",
)
async def liveness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    """Liveness probe - checks if the process is running."""
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description="Returns OK if the service is ready to accept traffic (Redis available).",
)
async def readiness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadinessResponse:
    """Readiness probe - checks if dependencies are available."""
    checks: dict[str, bool] = {}

    # Check Redis connectivity
    redis_ok = await _check_redis(settings.redis_url)
    checks["redis"] = redis_ok

    all_ok = all(checks.values())

    if not all_ok:
        logger.warning("readiness_check_failed", checks=checks)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "checks": checks},
        )

    return ReadinessResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        checks=checks,
    )


async def _check_redis(redis_url: str) -> bool:
    """Check Redis connectivity."""
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(redis_url, decode_responses=True)
        await client.ping()
        await client.aclose()
        return True
    except Exception as e:
        logger.error("redis_health_check_failed", error=str(e))
        return False
