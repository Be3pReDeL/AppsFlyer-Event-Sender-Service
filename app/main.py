"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.admin import router as admin_router
from app.api.health import router as health_router
from app.api.routes import router as tracking_router
from app.core.config import get_settings
from app.core.exceptions import AppError, AuthenticationError, ValidationError
from app.core.logging import get_logger, setup_logging

# Initialize logging before anything else
setup_logging()

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle - startup and shutdown events."""
    settings = get_settings()
    logger.info(
        "application_startup",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
    )

    # Startup: Initialize Redis connection pool
    try:
        app.state.redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=50,
        )
        await app.state.redis.ping()
        logger.info("redis_connected", url=_mask_redis_url(settings.redis_url))
    except Exception as e:
        logger.error("redis_connection_failed", error=str(e))
        # Allow startup even if Redis is down - readiness probe will fail
        app.state.redis = None

    yield

    # Shutdown: Clean up resources
    logger.info("application_shutdown")
    if hasattr(app.state, "redis") and app.state.redis:
        await app.state.redis.aclose()
        logger.info("redis_disconnected")


def _mask_redis_url(url: str) -> str:
    """Mask password in Redis URL for logging."""
    if "@" in url:
        # redis://:password@host:port/db -> redis://***@host:port/db
        parts = url.split("@")
        return f"redis://***@{parts[-1]}"
    return url


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Service for sending S2S events to AppsFlyer",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # Include routers
    app.include_router(health_router)
    app.include_router(tracking_router)
    app.include_router(admin_router)

    # Global exception handlers
    @app.exception_handler(AuthenticationError)
    async def auth_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:  # noqa: ARG001
        logger.warning(
            "authentication_error",
            error_type=type(exc).__name__,
            message=exc.message,
        )
        return JSONResponse(
            status_code=401,
            content={"error": exc.message, "details": exc.details},
        )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:  # noqa: ARG001
        logger.warning(
            "validation_error",
            error_type=type(exc).__name__,
            message=exc.message,
            details=exc.details,
        )
        return JSONResponse(
            status_code=400,
            content={"error": exc.message, "details": exc.details},
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:  # noqa: ARG001
        logger.warning(
            "app_error",
            error_type=type(exc).__name__,
            message=exc.message,
            details=exc.details,
        )
        return JSONResponse(
            status_code=400,
            content={"error": exc.message, "details": exc.details},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
        logger.exception("unhandled_exception", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )

    # Setup Prometheus metrics instrumentation
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_respect_env_var=False,  # Always enable metrics
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/health/live", "/health/ready", "/metrics"],
        inprogress_name="http_requests_inprogress",
        inprogress_labels=True,
    )
    instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    return app


# Create application instance
app = create_app()
