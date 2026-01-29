"""API routes for tracking events."""

import uuid
from datetime import datetime, timezone
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request, status

from app.api.auth import get_current_auth
from app.api.schemas import (
    ErrorResponse,
    PurchaseRequest,
    RegistrationRequest,
    TrackingResponse,
)
from app.core.config import Settings, get_settings
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.core.models import InternalEvent
from app.queue.producer import EventProducer, get_producer

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/track", tags=["Tracking"])


async def _get_redis(request: Request) -> aioredis.Redis:
    """Get Redis client from app state.

    Raises:
        HTTPException: 503 if Redis is not available
    """
    from fastapi import HTTPException

    redis = request.app.state.redis
    if redis is None:
        logger.error("redis_unavailable", message="Redis client not initialized")
        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable (Redis connection failed)",
        )
    return redis


async def _get_producer(
    redis: Annotated[aioredis.Redis, Depends(_get_redis)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EventProducer:
    """Get event producer instance."""
    return get_producer(redis, settings)


@router.get(
    "/registration",
    response_model=TrackingResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Track registration event (GET)",
    description="Track a registration event from query parameters. Requires authentication.",
    responses={
        202: {"description": "Event accepted and queued for processing"},
        400: {"model": ErrorResponse, "description": "Validation error"},
        401: {"model": ErrorResponse, "description": "Authentication failed"},
    },
)
async def track_registration_get(
    request: Request,
    auth: Annotated[dict, Depends(get_current_auth)],
    producer: Annotated[EventProducer, Depends(_get_producer)],
    app_id: str | None = None,
    appsflyer_id: str | None = None,
    customer_user_id: str | None = None,
    device_id: str | None = None,
    platform: str | None = None,
    registration_method: str | None = None,
    event_id: str | None = None,
) -> TrackingResponse:
    """Track registration event via GET request."""
    # Build request model from query parameters
    event_data = RegistrationRequest(
        app_id=app_id,
        appsflyer_id=appsflyer_id,
        customer_user_id=customer_user_id,
        device_id=device_id,
        platform=platform,
        registration_method=registration_method,
        event_id=event_id,
    )

    return await _process_registration(request, event_data, auth, producer)


@router.post(
    "/registration",
    response_model=TrackingResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Track registration event (POST)",
    description="Track a registration event from query parameters (Keitaro-compatible). Requires authentication.",
    responses={
        202: {"description": "Event accepted and queued for processing"},
        400: {"model": ErrorResponse, "description": "Validation error"},
        401: {"model": ErrorResponse, "description": "Authentication failed"},
    },
)
async def track_registration_post(
    request: Request,
    auth: Annotated[dict, Depends(get_current_auth)],
    producer: Annotated[EventProducer, Depends(_get_producer)],
    app_id: str | None = None,
    appsflyer_id: str | None = None,
    customer_user_id: str | None = None,
    device_id: str | None = None,
    platform: str | None = None,
    registration_method: str | None = None,
    event_id: str | None = None,
) -> TrackingResponse:
    """Track registration event via POST request (query parameters)."""
    # Build request model from query parameters (same as GET)
    event_data = RegistrationRequest(
        app_id=app_id,
        appsflyer_id=appsflyer_id,
        customer_user_id=customer_user_id,
        device_id=device_id,
        platform=platform,
        registration_method=registration_method,
        event_id=event_id,
    )

    return await _process_registration(request, event_data, auth, producer)


@router.get(
    "/purchase",
    response_model=TrackingResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Track purchase event (GET)",
    description="Track a purchase event from query parameters. Requires authentication.",
    responses={
        202: {"description": "Event accepted and queued for processing"},
        400: {"model": ErrorResponse, "description": "Validation error"},
        401: {"model": ErrorResponse, "description": "Authentication failed"},
    },
)
async def track_purchase_get(
    request: Request,
    auth: Annotated[dict, Depends(get_current_auth)],
    producer: Annotated[EventProducer, Depends(_get_producer)],
    app_id: str | None = None,
    revenue: float | None = None,
    currency: str | None = None,
    appsflyer_id: str | None = None,
    customer_user_id: str | None = None,
    device_id: str | None = None,
    platform: str | None = None,
    product_id: str | None = None,
    order_id: str | None = None,
    quantity: int | None = None,
    event_id: str | None = None,
) -> TrackingResponse:
    """Track purchase event via GET request."""
    # Validate required fields
    if revenue is None or currency is None:
        raise ValidationError(
            "Missing required fields",
            details={"required": ["revenue", "currency"]},
        )

    # Build request model from query parameters
    event_data = PurchaseRequest(
        app_id=app_id,
        revenue=revenue,
        currency=currency,
        appsflyer_id=appsflyer_id,
        customer_user_id=customer_user_id,
        device_id=device_id,
        platform=platform,
        product_id=product_id,
        order_id=order_id,
        quantity=quantity,
        event_id=event_id,
    )

    return await _process_purchase(request, event_data, auth, producer)


@router.post(
    "/purchase",
    response_model=TrackingResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Track purchase event (POST)",
    description="Track a purchase event from query parameters (Keitaro-compatible). Requires authentication.",
    responses={
        202: {"description": "Event accepted and queued for processing"},
        400: {"model": ErrorResponse, "description": "Validation error"},
        401: {"model": ErrorResponse, "description": "Authentication failed"},
    },
)
async def track_purchase_post(
    request: Request,
    auth: Annotated[dict, Depends(get_current_auth)],
    producer: Annotated[EventProducer, Depends(_get_producer)],
    app_id: str | None = None,
    revenue: float | None = None,
    currency: str | None = None,
    appsflyer_id: str | None = None,
    customer_user_id: str | None = None,
    device_id: str | None = None,
    platform: str | None = None,
    product_id: str | None = None,
    order_id: str | None = None,
    quantity: int | None = None,
    event_id: str | None = None,
) -> TrackingResponse:
    """Track purchase event via POST request (query parameters)."""
    from fastapi import HTTPException
    from pydantic import ValidationError as PydanticValidationError

    # Validate required fields
    if revenue is None or currency is None:
        raise ValidationError(
            "Missing required fields",
            details={"required": ["revenue", "currency"]},
        )

    # Build request model from query parameters (same as GET)
    try:
        event_data = PurchaseRequest(
            app_id=app_id,
            revenue=revenue,
            currency=currency,
            appsflyer_id=appsflyer_id,
            customer_user_id=customer_user_id,
            device_id=device_id,
            platform=platform,
            product_id=product_id,
            order_id=order_id,
            quantity=quantity,
            event_id=event_id,
        )
    except PydanticValidationError as e:
        # Convert Pydantic validation error to HTTP 422
        raise HTTPException(status_code=422, detail=e.errors()) from e

    return await _process_purchase(request, event_data, auth, producer)


async def _process_registration(
    request: Request,  # noqa: ARG001
    event_data: RegistrationRequest,
    auth: dict,
    producer: Annotated[EventProducer, Depends(_get_producer)],
) -> TrackingResponse:
    """Process registration event (common logic for GET/POST)."""
    # Generate event_id if not provided
    final_event_id = event_data.event_id or f"reg_{uuid.uuid4().hex[:16]}"
    queued_at = datetime.now(timezone.utc)

    # Check for duplicates
    is_duplicate = await producer.check_duplicate(final_event_id)
    if is_duplicate:
        logger.info(
            "duplicate_event_skipped",
            event_id=final_event_id,
            event_type="registration",
        )
        return TrackingResponse(
            status="accepted",
            event_id=final_event_id,
            queued_at=queued_at,
            message="Duplicate event (already processed)",
        )

    # Build internal event
    internal_event = InternalEvent(
        event_type="registration",
        event_id=final_event_id,
        received_at=queued_at,
        payload=event_data.model_dump(exclude_none=True),
        attempt=0,
        source_meta={
            "auth_method": auth["method"],
        },
    )

    # Enqueue to Redis Streams
    await producer.enqueue(internal_event)

    # Mark as processed for deduplication
    await producer.mark_processed(final_event_id)

    logger.info(
        "registration_received",
        event_id=final_event_id,
        auth_method=auth["method"],
        platform=event_data.platform,
        has_appsflyer_id=event_data.appsflyer_id is not None,
        has_customer_user_id=event_data.customer_user_id is not None,
    )

    return TrackingResponse(
        status="accepted",
        event_id=final_event_id,
        queued_at=queued_at,
        message="Event queued for processing",
    )


async def _process_purchase(
    request: Request,  # noqa: ARG001
    event_data: PurchaseRequest,
    auth: dict,
    producer: Annotated[EventProducer, Depends(_get_producer)],
) -> TrackingResponse:
    """Process purchase event (common logic for GET/POST)."""
    # Generate event_id if not provided
    final_event_id = event_data.event_id or f"purchase_{uuid.uuid4().hex[:16]}"
    queued_at = datetime.now(timezone.utc)

    # Check for duplicates
    is_duplicate = await producer.check_duplicate(final_event_id)
    if is_duplicate:
        logger.info(
            "duplicate_event_skipped",
            event_id=final_event_id,
            event_type="purchase",
        )
        return TrackingResponse(
            status="accepted",
            event_id=final_event_id,
            queued_at=queued_at,
            message="Duplicate event (already processed)",
        )

    # Build internal event
    internal_event = InternalEvent(
        event_type="purchase",
        event_id=final_event_id,
        received_at=queued_at,
        payload=event_data.model_dump(exclude_none=True),
        attempt=0,
        source_meta={
            "auth_method": auth["method"],
        },
    )

    # Enqueue to Redis Streams
    await producer.enqueue(internal_event)

    # Mark as processed for deduplication
    await producer.mark_processed(final_event_id)

    logger.info(
        "purchase_received",
        event_id=final_event_id,
        auth_method=auth["method"],
        platform=event_data.platform,
        revenue=event_data.revenue,
        currency=event_data.currency,
        has_appsflyer_id=event_data.appsflyer_id is not None,
        has_customer_user_id=event_data.customer_user_id is not None,
    )

    return TrackingResponse(
        status="accepted",
        event_id=final_event_id,
        queued_at=queued_at,
        message="Event queued for processing",
    )
