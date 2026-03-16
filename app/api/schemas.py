"""Pydantic schemas for API requests and responses."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TrackingRequestBase(BaseModel):
    """Base model for tracking requests."""

    # AppsFlyer target app
    app_id: str | None = Field(
        None,
        description="AppsFlyer app ID (for iOS: id123456789, for Android: com.example.app). Uses default if not provided.",
    )
    dev_key: str | None = Field(
        None,
        description="AppsFlyer dev key override for this request. If omitted, APPSFLYER_DEV_KEY from env is used.",
    )

    # AppsFlyer identifiers
    appsflyer_id: str | None = Field(None, description="AppsFlyer device ID")
    customer_user_id: str | None = Field(None, description="Customer user ID")

    # Device/platform info
    device_id: str | None = Field(None, description="Device identifier")
    platform: str | None = Field(None, description="Platform (iOS/Android)")
    app_version: str | None = Field(None, description="App version")

    # Event metadata
    event_time: datetime | None = Field(None, description="Event timestamp")
    event_id: str | None = Field(None, description="Unique event identifier for deduplication")

    # Additional custom parameters
    custom_data: dict[str, Any] = Field(default_factory=dict, description="Custom event parameters")

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, v: str | None) -> str | None:
        """Validate platform value."""
        if v is not None and v.lower() not in ["ios", "android", "web", ""]:
            # Don't raise error, just normalize
            return v.lower()
        return v.lower() if v else None


class RegistrationRequest(TrackingRequestBase):
    """Request model for registration events."""

    # Registration-specific fields
    registration_method: str | None = Field(None, description="Registration method (email, social, etc)")
    user_email: str | None = Field(None, description="User email")

    class Config:
        json_schema_extra = {
            "example": {
                "appsflyer_id": "1234567890-1234567890",
                "customer_user_id": "user123",
                "platform": "ios",
                "registration_method": "email",
                "event_id": "reg_abc123",
            }
        }


class PurchaseRequest(TrackingRequestBase):
    """Request model for purchase events."""

    # Purchase-specific fields (required for AppsFlyer)
    revenue: float = Field(..., description="Purchase revenue", ge=0)
    currency: str = Field(..., description="Currency code (ISO 4217)", min_length=3, max_length=3)

    # Optional purchase details
    product_id: str | None = Field(None, description="Product identifier")
    quantity: int | None = Field(None, description="Quantity purchased", ge=1)
    order_id: str | None = Field(None, description="Order/transaction ID")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Normalize currency to uppercase."""
        return v.upper()

    class Config:
        json_schema_extra = {
            "example": {
                "appsflyer_id": "1234567890-1234567890",
                "customer_user_id": "user123",
                "platform": "android",
                "revenue": 9.99,
                "currency": "USD",
                "product_id": "premium_monthly",
                "order_id": "order_xyz789",
                "event_id": "purchase_def456",
            }
        }


class TrackingResponse(BaseModel):
    """Response model for tracking endpoints."""

    status: str = Field(..., description="Status of the request")
    event_id: str = Field(..., description="Event identifier")
    queued_at: datetime = Field(..., description="Time when event was queued")
    message: str | None = Field(None, description="Additional message")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "accepted",
                "event_id": "evt_1234567890",
                "queued_at": "2026-01-29T12:34:56Z",
                "message": "Event queued for processing",
            }
        }


class DevKeyMappingUpsertRequest(BaseModel):
    """Request model for app_id -> dev_key mapping update."""

    app_id: str = Field(..., min_length=1, description="AppsFlyer app ID")
    dev_key: str = Field(..., min_length=1, description="AppsFlyer dev key for the app")


class DevKeyMappingResponse(BaseModel):
    """Response model for app_id -> dev_key mapping update."""

    status: str = Field(..., description="Update status")
    app_id: str = Field(..., description="AppsFlyer app ID")
    updated_at: datetime = Field(..., description="UTC timestamp when mapping was updated")


class ErrorResponse(BaseModel):
    """Error response model."""

    error: str = Field(..., description="Error message")
    details: dict[str, Any] = Field(default_factory=dict, description="Error details")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "Validation failed",
                "details": {"field": "revenue", "reason": "must be positive"},
            }
        }
