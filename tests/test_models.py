"""Tests for internal data models."""

from datetime import datetime, timezone

from app.core.models import InternalEvent


def test_internal_event_serialization_roundtrip() -> None:
    """Test that InternalEvent can be serialized and deserialized correctly."""
    # Create event with complex payload and source_meta
    original = InternalEvent(
        event_type="purchase",
        event_id="test_evt_123",
        received_at=datetime(2026, 1, 29, 12, 30, 45, tzinfo=timezone.utc),
        payload={
            "appsflyer_id": "device-456",
            "revenue": 19.99,
            "currency": "USD",
            "nested": {"key": "value", "number": 42},
        },
        attempt=3,
        source_meta={
            "auth_method": "hmac",
            "ip": "192.168.1.1",
        },
    )

    # Serialize to stream fields
    fields = original.to_stream_fields()

    # Verify all fields are strings
    assert all(isinstance(v, str) for v in fields.values())

    # Verify field content
    assert fields["event_type"] == "purchase"
    assert fields["event_id"] == "test_evt_123"
    assert fields["received_at"] == "2026-01-29T12:30:45+00:00"
    assert fields["attempt"] == "3"

    # Verify payload and source_meta are valid JSON strings (not wrapped)
    import json

    payload_data = json.loads(fields["payload"])
    assert payload_data["appsflyer_id"] == "device-456"
    assert payload_data["revenue"] == 19.99
    assert payload_data["nested"]["number"] == 42

    source_meta_data = json.loads(fields["source_meta"])
    assert source_meta_data["auth_method"] == "hmac"
    assert source_meta_data["ip"] == "192.168.1.1"

    # Deserialize from stream fields
    reconstructed = InternalEvent.from_stream_fields(fields)

    # Verify reconstruction matches original
    assert reconstructed.event_type == original.event_type
    assert reconstructed.event_id == original.event_id
    assert reconstructed.received_at == original.received_at
    assert reconstructed.payload == original.payload
    assert reconstructed.attempt == original.attempt
    assert reconstructed.source_meta == original.source_meta


def test_internal_event_empty_dicts() -> None:
    """Test serialization with empty payload and source_meta."""
    event = InternalEvent(
        event_type="registration",
        event_id="evt_empty",
        received_at=datetime.now(timezone.utc),
        payload={},
        attempt=0,
        source_meta={},
    )

    fields = event.to_stream_fields()
    reconstructed = InternalEvent.from_stream_fields(fields)

    assert reconstructed.payload == {}
    assert reconstructed.source_meta == {}
