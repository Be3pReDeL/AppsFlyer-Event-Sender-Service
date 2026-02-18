"""Integration tests for end-to-end flows."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.core.models import InternalEvent
from app.queue.consumer import EventConsumer
from app.queue.producer import EventProducer


@pytest.mark.asyncio
async def test_producer_consumer_integration() -> None:
    """Test end-to-end flow: produce event, consume event."""
    # Create mock Redis
    mock_redis = AsyncMock()

    # Mock xadd to return message ID
    mock_redis.xadd.return_value = "1234567890-0"

    # Mock xreadgroup to return the event
    event = InternalEvent(
        event_type="registration",
        event_id="test_evt_123",
        received_at=datetime.now(timezone.utc),
        payload={"appsflyer_id": "device-123"},
        attempt=0,
        source_meta={"auth_method": "token"},
    )

    mock_redis.xreadgroup.return_value = [
        [
            "events:main",
            [
                (
                    "1234567890-0",
                    event.to_stream_fields(),
                )
            ],
        ]
    ]

    settings = Settings(
        redis_url="redis://localhost:6379/0",
        stream_main="events:main",
        stream_dlq="events:dlq",
        worker_consumer_group="test_group",
        dedup_ttl_seconds=3600,
    )

    # Test producer
    producer = EventProducer(mock_redis, settings)
    message_id = await producer.enqueue(event)
    assert message_id == "1234567890-0"

    # Test consumer
    consumer = EventConsumer(mock_redis, settings)
    events = await consumer.read_events(count=10, block_ms=1000)

    assert len(events) == 1
    read_message_id, read_event = events[0]
    assert read_message_id == "1234567890-0"
    assert read_event.event_id == "test_evt_123"
    assert read_event.event_type == "registration"

    # Test acknowledgment
    await consumer.ack_message(message_id)
    mock_redis.xack.assert_called_once()


@pytest.mark.asyncio
async def test_deduplication_flow() -> None:
    """Test deduplication prevents duplicate processing."""
    mock_redis = AsyncMock()
    settings = Settings(dedup_ttl_seconds=3600)

    producer = EventProducer(mock_redis, settings)

    # First check - not duplicate
    mock_redis.exists.return_value = 0
    is_dup1 = await producer.check_duplicate("event_123")
    assert is_dup1 is False

    # Mark as processed
    await producer.mark_processed("event_123")
    mock_redis.setex.assert_called_once_with("dedup:event_123", 3600, "1")

    # Second check - is duplicate
    mock_redis.exists.return_value = 1
    is_dup2 = await producer.check_duplicate("event_123")
    assert is_dup2 is True
