"""AppsFlyer API models."""

from typing import Any

from pydantic import BaseModel, Field


class AppsFlyerRequest(BaseModel):
    """AppsFlyer S2S in-app event request model."""

    appsflyer_id: str = Field(..., description="AppsFlyer unique device ID")
    event_name: str = Field(..., description="Event name (af_purchase, af_complete_registration)")
    event_value: dict[str, Any] = Field(
        default_factory=dict,
        description="Event parameters (af_revenue, af_currency, etc)",
    )
    customer_user_id: str | None = Field(None, description="Customer user ID")
    platform: str | None = Field(None, description="Platform (iOS, Android)")
    event_time: str | None = Field(None, description="ISO 8601 timestamp")
    device_ids: dict[str, str] | None = Field(None, description="Device identifiers")
    ip: str | None = Field(None, description="Device IP address")
    app_version: str | None = Field(None, description="App version")


class AppsFlyerResponse(BaseModel):
    """AppsFlyer API response model."""

    status: str = Field(..., description="Response status")
    message: str | None = Field(None, description="Response message")
