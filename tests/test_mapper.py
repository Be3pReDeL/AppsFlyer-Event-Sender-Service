"""Tests for AppsFlyer mapper."""

from datetime import datetime, timezone

import pytest

from app.appsflyer.mapper import AppsFlyerMapper
from app.core.models import InternalEvent


def test_map_registration_event() -> None:
    """Test mapping registration event."""
    event = InternalEvent(
        event_type="registration",
        event_id="reg_123",
        received_at=datetime(2026, 1, 29, 12, 0, 0, tzinfo=timezone.utc),
        payload={
            "appsflyer_id": "af-device-123",
            "customer_user_id": "user-456",
            "platform": "ios",
            "registration_method": "email",
        },
        attempt=0,
        source_meta={},
    )

    request, app_id = AppsFlyerMapper.map_event(event)

    assert request.appsflyer_id == "af-device-123"
    assert request.event_name == "af_complete_registration"
    assert request.customer_user_id == "user-456"
    assert request.platform == "iOS"
    assert request.event_value.get("af_registration_method") == "email"
    assert app_id is None  # Not provided in payload


def test_map_purchase_event() -> None:
    """Test mapping purchase event."""
    event = InternalEvent(
        event_type="purchase",
        event_id="purchase_456",
        received_at=datetime(2026, 1, 29, 12, 0, 0, tzinfo=timezone.utc),
        payload={
            "appsflyer_id": "af-device-789",
            "customer_user_id": "user-789",
            "platform": "android",
            "revenue": 19.99,
            "currency": "USD",
            "product_id": "premium_monthly",
            "quantity": 1,
            "order_id": "order_abc123",
        },
        attempt=0,
        source_meta={},
    )

    request, app_id = AppsFlyerMapper.map_event(event)

    assert request.appsflyer_id == "af-device-789"
    assert request.event_name == "af_purchase"
    assert request.customer_user_id == "user-789"
    assert request.platform == "Android"
    assert request.event_value["af_revenue"] == "19.99"
    assert request.event_value["af_currency"] == "USD"
    assert request.event_value["af_content_id"] == "premium_monthly"
    assert request.event_value["af_quantity"] == 1
    assert request.event_value["af_order_id"] == "order_abc123"
    assert app_id is None


def test_map_event_with_app_id() -> None:
    """Test that app_id is extracted from payload."""
    event = InternalEvent(
        event_type="registration",
        event_id="evt_app",
        received_at=datetime.now(timezone.utc),
        payload={
            "app_id": "id123456789",  # iOS app
            "appsflyer_id": "af-dev-123",
            "platform": "ios",
        },
        attempt=0,
        source_meta={},
    )

    request, app_id = AppsFlyerMapper.map_event(event)
    assert app_id == "id123456789"


def test_map_event_missing_appsflyer_id() -> None:
    """Test that missing appsflyer_id raises ValueError."""
    event = InternalEvent(
        event_type="registration",
        event_id="evt_bad",
        received_at=datetime.now(timezone.utc),
        payload={"platform": "ios"},  # No appsflyer_id or device_id
        attempt=0,
        source_meta={},
    )

    with pytest.raises(ValueError, match="Missing appsflyer_id"):
        AppsFlyerMapper.map_event(event)


def test_map_event_fallback_to_device_id() -> None:
    """Test that device_id is used as fallback for appsflyer_id."""
    event = InternalEvent(
        event_type="registration",
        event_id="evt_123",
        received_at=datetime.now(timezone.utc),
        payload={
            "device_id": "device-xyz",  # No appsflyer_id, use device_id
            "platform": "android",
        },
        attempt=0,
        source_meta={},
    )

    request, _ = AppsFlyerMapper.map_event(event)
    assert request.appsflyer_id == "device-xyz"


def test_map_event_with_device_ids() -> None:
    """Test mapping with advertising IDs."""
    event = InternalEvent(
        event_type="purchase",
        event_id="evt_456",
        received_at=datetime.now(timezone.utc),
        payload={
            "appsflyer_id": "af-dev-123",
            "advertising_id": "ad-id-123",
            "idfa": "idfa-456",
            "revenue": 9.99,
            "currency": "EUR",
        },
        attempt=0,
        source_meta={},
    )

    request, _ = AppsFlyerMapper.map_event(event)
    assert request.device_ids is not None
    assert request.device_ids["advertising_id"] == "ad-id-123"
    assert request.device_ids["idfa"] == "idfa-456"


def test_map_event_platform_normalization() -> None:
    """Test platform normalization."""
    test_cases = [
        ("ios", "iOS"),
        ("iOS", "iOS"),
        ("iphone", "iOS"),
        ("ipad", "iOS"),
        ("android", "Android"),
        ("Android", "Android"),
        ("windows", "Windows"),
        ("unknown", "unknown"),  # Unknown platforms kept as-is
    ]

    for input_platform, expected_platform in test_cases:
        event = InternalEvent(
            event_type="registration",
            event_id=f"evt_{input_platform}",
            received_at=datetime.now(timezone.utc),
            payload={
                "appsflyer_id": "af-dev-123",
                "platform": input_platform,
            },
            attempt=0,
            source_meta={},
        )

        request, _ = AppsFlyerMapper.map_event(event)
        assert request.platform == expected_platform


def test_map_event_with_custom_data() -> None:
    """Test that custom_data is merged into event_value."""
    event = InternalEvent(
        event_type="registration",
        event_id="evt_custom",
        received_at=datetime.now(timezone.utc),
        payload={
            "appsflyer_id": "af-dev-123",
            "custom_data": {
                "user_segment": "premium",
                "referral_code": "FRIEND123",
            },
        },
        attempt=0,
        source_meta={},
    )

    request, _ = AppsFlyerMapper.map_event(event)
    assert request.event_value["user_segment"] == "premium"
    assert request.event_value["referral_code"] == "FRIEND123"
