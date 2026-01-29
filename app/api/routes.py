"""API routes for tracking events."""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.auth import get_current_auth
from app.api.schemas import (
    ErrorResponse,
    PurchaseRequest,
    RegistrationRequest,
    TrackingResponse,
)
from app.core.exceptions import ValidationError
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/track", tags=["Tracking"])


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
        appsflyer_id=appsflyer_id,
        customer_user_id=customer_user_id,
        device_id=device_id,
        platform=platform,
        registration_method=registration_method,
        event_id=event_id,
    )

    return await _process_registration(request, event_data, auth)


@router.post(
    "/registration",
    response_model=TrackingResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Track registration event (POST)",
    description="Track a registration event from JSON body. Requires authentication via query parameter.",
    responses={
        202: {"description": "Event accepted and queued for processing"},
        400: {"model": ErrorResponse, "description": "Validation error"},
        401: {"model": ErrorResponse, "description": "Authentication failed"},
    },
)
async def track_registration_post(
    request: Request,
    event_data: RegistrationRequest,
    auth: Annotated[dict, Depends(get_current_auth)],
) -> TrackingResponse:
    """Track registration event via POST request."""
    return await _process_registration(request, event_data, auth)


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

    return await _process_purchase(request, event_data, auth)


@router.post(
    "/purchase",
    response_model=TrackingResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Track purchase event (POST)",
    description="Track a purchase event from JSON body. Requires authentication via query parameter.",
    responses={
        202: {"description": "Event accepted and queued for processing"},
        400: {"model": ErrorResponse, "description": "Validation error"},
        401: {"model": ErrorResponse, "description": "Authentication failed"},
    },
)
async def track_purchase_post(
    request: Request,
    event_data: PurchaseRequest,
    auth: Annotated[dict, Depends(get_current_auth)],
) -> TrackingResponse:
    """Track purchase event via POST request."""
    return await _process_purchase(request, event_data, auth)


async def _process_registration(
    request: Request,  # noqa: ARG001
    event_data: RegistrationRequest,
    auth: dict,
) -> TrackingResponse:
    """Process registration event (common logic for GET/POST)."""
    # Generate event_id if not provided
    final_event_id = event_data.event_id or f"reg_{uuid.uuid4().hex[:16]}"
    queued_at = datetime.now(timezone.utc)

    # Log event reception (with masked sensitive data)
    logger.info(
        "registration_received",
        event_id=final_event_id,
        auth_method=auth["method"],
        platform=event_data.platform,
        has_appsflyer_id=event_data.appsflyer_id is not None,
        has_customer_user_id=event_data.customer_user_id is not None,
    )

    # TODO: Next stage - enqueue to Redis Streams
    # For now, just return success response

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
) -> TrackingResponse:
    """Process purchase event (common logic for GET/POST)."""
    # Generate event_id if not provided
    final_event_id = event_data.event_id or f"purchase_{uuid.uuid4().hex[:16]}"
    queued_at = datetime.now(timezone.utc)

    # Log event reception (with masked sensitive data)
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

    # TODO: Next stage - enqueue to Redis Streams
    # For now, just return success response

    return TrackingResponse(
        status="accepted",
        event_id=final_event_id,
        queued_at=queued_at,
        message="Event queued for processing",
    )
