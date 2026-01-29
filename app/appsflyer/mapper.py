"""Mapper for converting InternalEvent to AppsFlyer API request."""

from typing import Any

from app.appsflyer.models import AppsFlyerRequest
from app.core.logging import get_logger
from app.core.models import InternalEvent

logger = get_logger(__name__)


class AppsFlyerMapper:
    """Maps internal events to AppsFlyer API requests."""

    # Event name mapping
    EVENT_NAMES = {
        "registration": "af_complete_registration",
        "purchase": "af_purchase",
    }

    @staticmethod
    def map_event(event: InternalEvent) -> tuple[AppsFlyerRequest, str | None]:
        """Map InternalEvent to AppsFlyerRequest.

        Args:
            event: Internal event from queue

        Returns:
            Tuple of (AppsFlyer API request model, app_id or None)

        Raises:
            ValueError: If required fields are missing
        """
        payload = event.payload

        # Extract app_id if provided
        app_id = payload.get("app_id")

        # Get AppsFlyer ID (required)
        appsflyer_id = payload.get("appsflyer_id") or payload.get("device_id")
        if not appsflyer_id:
            raise ValueError("Missing appsflyer_id or device_id in payload")

        # Get event name
        event_name = AppsFlyerMapper.EVENT_NAMES.get(
            event.event_type,
            event.event_type,  # Use as-is if not in mapping
        )

        # Build event_value based on event type
        event_value = AppsFlyerMapper._build_event_value(event.event_type, payload)

        # Build device_ids if advertising IDs are available
        device_ids = AppsFlyerMapper._build_device_ids(payload)

        # Format event_time if available
        event_time = None
        if payload.get("event_time"):
            # Convert datetime to ISO format string if needed
            from datetime import datetime

            evt = payload["event_time"]
            event_time = evt.isoformat() if isinstance(evt, datetime) else str(evt)
        elif event.received_at:
            event_time = event.received_at.isoformat()

        request = AppsFlyerRequest(
            appsflyer_id=appsflyer_id,
            event_name=event_name,
            event_value=event_value,
            customer_user_id=payload.get("customer_user_id"),
            platform=AppsFlyerMapper._normalize_platform(payload.get("platform")),
            event_time=event_time,
            device_ids=device_ids,
            app_version=payload.get("app_version"),
        )

        logger.debug(
            "event_mapped",
            event_id=event.event_id,
            event_type=event.event_type,
            appsflyer_event_name=event_name,
            app_id=app_id,
        )

        return request, app_id

    @staticmethod
    def _build_event_value(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Build event_value dict based on event type.

        Args:
            event_type: Internal event type
            payload: Event payload

        Returns:
            Event value dict for AppsFlyer
        """
        event_value: dict[str, Any] = {}

        if event_type == "purchase":
            # Purchase-specific fields
            if "revenue" in payload:
                # AppsFlyer expects string for af_revenue
                event_value["af_revenue"] = str(payload["revenue"])

            if "currency" in payload:
                event_value["af_currency"] = payload["currency"]

            if "product_id" in payload:
                event_value["af_content_id"] = payload["product_id"]

            if "quantity" in payload:
                event_value["af_quantity"] = payload["quantity"]

            if "order_id" in payload:
                event_value["af_order_id"] = payload["order_id"]

        elif event_type == "registration":
            # Registration-specific fields
            if "registration_method" in payload:
                event_value["af_registration_method"] = payload["registration_method"]

        # Add any custom data
        if "custom_data" in payload and isinstance(payload["custom_data"], dict):
            event_value.update(payload["custom_data"])

        return event_value

    @staticmethod
    def _build_device_ids(payload: dict[str, Any]) -> dict[str, str] | None:
        """Build device_ids object if advertising IDs are present.

        Args:
            payload: Event payload

        Returns:
            Device IDs dict or None
        """
        device_ids: dict[str, str] = {}

        # Check for advertising IDs in payload
        if "advertising_id" in payload:
            device_ids["advertising_id"] = payload["advertising_id"]

        if "idfa" in payload:
            device_ids["idfa"] = payload["idfa"]

        if "android_id" in payload:
            device_ids["android_id"] = payload["android_id"]

        return device_ids if device_ids else None

    @staticmethod
    def _normalize_platform(platform: str | None) -> str | None:
        """Normalize platform name to AppsFlyer format.

        Args:
            platform: Platform string

        Returns:
            Normalized platform or None
        """
        if not platform:
            return None

        platform_lower = platform.lower()

        # Map to AppsFlyer expected values
        if platform_lower in ["ios", "iphone", "ipad"]:
            return "iOS"
        elif platform_lower in ["android"]:
            return "Android"
        elif platform_lower in ["windows"]:
            return "Windows"

        # Return as-is if unknown
        return platform
