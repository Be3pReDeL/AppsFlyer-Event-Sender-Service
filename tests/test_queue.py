"""Tests for queue producer and consumer."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.core.models import InternalEvent
from app.queue.consumer import EventConsumer
from app.queue.producer import EventProducer


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Create a mock Redis client."""
    return AsyncMock()


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        redis_url="redis://localhost:6379/0",
        stream_main="test:main",
        stream_dlq="test:dlq",
        worker_consumer_group="test_group",
        dedup_ttl_seconds=3600,
    )


@pytest.fixture
def sample_event() -> InternalEvent:
    """Create a sample internal event."""
    return InternalEvent(
        event_type="registration",
        event_id="test_event_123",
        received_at=datetime.now(timezone.utc),
        payload={"appsflyer_id": "device-123", "platform": "ios"},
        attempt=0,
        source_meta={"auth_method": "token"},
    )


class TestEventProducer:
    """Tests for EventProducer."""

    async def test_enqueue_success(
        self,
        mock_redis: AsyncMock,
        settings: Settings,
        sample_event: InternalEvent,
    ) -> None:
        """Test successful event enqueueing."""
        mock_redis.xadd.return_value = "1234567890-0"
        producer = EventProducer(mock_redis, settings)

        message_id = await producer.enqueue(sample_event)

        assert message_id == "1234567890-0"
        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args
        assert call_args.kwargs["name"] == "test:main"
        assert "event_id" in call_args.kwargs["fields"]

    async def test_check_duplicate_exists(
        self,
        mock_redis: AsyncMock,
        settings: Settings,
    ) -> None:
        """Test duplicate check when event exists."""
        mock_redis.exists.return_value = 1
        producer = EventProducer(mock_redis, settings)

        is_duplicate = await producer.check_duplicate("event_123")

        assert is_duplicate is True
        mock_redis.exists.assert_called_once_with("dedup:event_123")

    async def test_check_duplicate_not_exists(
        self,
        mock_redis: AsyncMock,
        settings: Settings,
    ) -> None:
        """Test duplicate check when event does not exist."""
        mock_redis.exists.return_value = 0
        producer = EventProducer(mock_redis, settings)

        is_duplicate = await producer.check_duplicate("event_123")

        assert is_duplicate is False

    async def test_mark_processed(
        self,
        mock_redis: AsyncMock,
        settings: Settings,
    ) -> None:
        """Test marking event as processed."""
        producer = EventProducer(mock_redis, settings)

        await producer.mark_processed("event_123")

        mock_redis.setex.assert_called_once_with("dedup:event_123", 3600, "1")

    async def test_move_to_dlq(
        self,
        mock_redis: AsyncMock,
        settings: Settings,
        sample_event: InternalEvent,
    ) -> None:
        """Test moving event to DLQ."""
        mock_redis.xadd.return_value = "dlq-msg-id"
        producer = EventProducer(mock_redis, settings)

        await producer.move_to_dlq(sample_event, "max_retries_exceeded", "Last error msg")

        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args
        assert call_args.kwargs["name"] == "test:dlq"
        fields = call_args.kwargs["fields"]
        assert fields["dlq_reason"] == "max_retries_exceeded"
        assert fields["last_error"] == "Last error msg"


class TestEventConsumer:
    """Tests for EventConsumer."""

    async def test_ensure_consumer_group_new(
        self,
        mock_redis: AsyncMock,
        settings: Settings,
    ) -> None:
        """Test creating new consumer group."""
        consumer = EventConsumer(mock_redis, settings)

        await consumer.ensure_consumer_group()

        mock_redis.xgroup_create.assert_called_once_with(
            name="test:main",
            groupname="test_group",
            id="0",
            mkstream=True,
        )

    async def test_ensure_consumer_group_exists(
        self,
        mock_redis: AsyncMock,
        settings: Settings,
    ) -> None:
        """Test when consumer group already exists."""
        mock_redis.xgroup_create.side_effect = Exception("BUSYGROUP Consumer Group name already exists")
        consumer = EventConsumer(mock_redis, settings)

        # Should not raise
        await consumer.ensure_consumer_group()

    async def test_read_events_success(
        self,
        mock_redis: AsyncMock,
        settings: Settings,
    ) -> None:
        """Test reading events from stream."""
        # Mock xreadgroup response: [[stream_name, [(message_id, fields)]]]
        mock_redis.xreadgroup.return_value = [
            [
                "test:main",
                [
                    (
                        "1234567890-0",
                        {
                            "event_type": "registration",
                            "event_id": "evt_123",
                            "received_at": datetime.now(timezone.utc).isoformat(),
                            "payload": '{"appsflyer_id": "dev-123"}',
                            "attempt": "0",
                            "source_meta": "{}",
                        },
                    )
                ],
            ]
        ]

        consumer = EventConsumer(mock_redis, settings)
        events = await consumer.read_events(count=10, block_ms=5000)

        assert len(events) == 1
        message_id, event = events[0]
        assert message_id == "1234567890-0"
        assert event.event_id == "evt_123"
        assert event.event_type == "registration"

    async def test_read_events_empty(
        self,
        mock_redis: AsyncMock,
        settings: Settings,
    ) -> None:
        """Test reading when no events available."""
        mock_redis.xreadgroup.return_value = None
        consumer = EventConsumer(mock_redis, settings)

        events = await consumer.read_events()

        assert len(events) == 0

    async def test_ack_message(
        self,
        mock_redis: AsyncMock,
        settings: Settings,
    ) -> None:
        """Test acknowledging a message."""
        consumer = EventConsumer(mock_redis, settings)

        await consumer.ack_message("1234567890-0")

        mock_redis.xack.assert_called_once_with(
            "test:main",
            "test_group",
            "1234567890-0",
        )
