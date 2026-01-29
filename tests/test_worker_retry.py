"""Tests for worker retry logic and DLQ handling."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.asyncio as aioredis

from app.appsflyer.client import AppsFlyerClient
from app.core.config import get_settings
from app.core.exceptions import AppsFlyerError
from app.core.models import InternalEvent
from app.queue.consumer import EventConsumer
from app.queue.producer import EventProducer
from app.worker.run import Worker


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    return AsyncMock(spec=aioredis.Redis)


@pytest.fixture
def mock_consumer():
    """Create mock EventConsumer."""
    consumer = AsyncMock(spec=EventConsumer)
    consumer.consumer_name = "test-worker"
    return consumer


@pytest.fixture
def mock_producer():
    """Create mock EventProducer."""
    return AsyncMock(spec=EventProducer)


@pytest.fixture
def mock_appsflyer_client():
    """Create mock AppsFlyerClient."""
    return AsyncMock(spec=AppsFlyerClient)


@pytest.fixture
def worker(mock_redis, mock_consumer, mock_producer, mock_appsflyer_client):
    """Create Worker instance with mocked dependencies."""
    settings = get_settings()
    w = Worker()
    w.settings = settings
    w.redis = mock_redis
    w.consumer = mock_consumer
    w.producer = mock_producer
    w.appsflyer_client = mock_appsflyer_client
    w.running = True
    return w


@pytest.fixture
def sample_event():
    """Create sample InternalEvent."""
    return InternalEvent(
        event_type="registration",
        event_id="test-event-123",
        received_at=datetime.now(timezone.utc),
        payload={
            "appsflyer_id": "device-123",
            "platform": "ios",
        },
        attempt=0,
        source_meta={
            "ip": "1.2.3.4",
            "user_agent": "TestAgent/1.0",
        },
    )


@pytest.mark.asyncio
async def test_backoff_calculation(worker):
    """Test exponential backoff with jitter calculation."""
    # Attempt 0: ~1s ± 0.25s
    delay0 = worker._calculate_backoff(0)
    assert 0.75 <= delay0 <= 1.25

    # Attempt 1: ~2s ± 0.5s
    delay1 = worker._calculate_backoff(1)
    assert 1.5 <= delay1 <= 2.5

    # Attempt 2: ~4s ± 1s
    delay2 = worker._calculate_backoff(2)
    assert 3.0 <= delay2 <= 5.0

    # Attempt 10: capped at max (60s by default) + jitter (±25%)
    delay10 = worker._calculate_backoff(10)
    assert delay10 <= 75.0  # 60 * 1.25 = 75s (max with jitter)


@pytest.mark.asyncio
async def test_max_attempts_exceeded_moves_to_dlq(
    worker, sample_event, mock_producer, mock_consumer
):
    """Test that events exceeding max attempts are moved to DLQ."""
    sample_event.attempt = 8  # >= MAX_ATTEMPTS (8)

    await worker._process_event("msg-123", sample_event)

    # Should move to DLQ
    mock_producer.move_to_dlq.assert_called_once()
    call_args = mock_producer.move_to_dlq.call_args
    assert call_args[1]["event"] == sample_event
    assert call_args[1]["reason"] == "max_attempts_exceeded"

    # Should ack message
    mock_consumer.ack_message.assert_called_once_with("msg-123")


@pytest.mark.asyncio
async def test_non_retryable_error_moves_to_dlq(
    worker, sample_event, mock_producer, mock_consumer, mock_appsflyer_client
):
    """Test that non-retryable AppsFlyer errors move event to DLQ."""
    with patch("app.appsflyer.mapper.AppsFlyerMapper.map_event") as mock_map:
        mock_map.return_value = (MagicMock(), "id123456789")

        # Simulate 400 error (non-retryable)
        mock_appsflyer_client.send_event.side_effect = AppsFlyerError(
            "Invalid request",
            status_code=400,
            retryable=False,
        )

        await worker._process_event("msg-123", sample_event)

        # Should move to DLQ
        mock_producer.move_to_dlq.assert_called_once()
        call_args = mock_producer.move_to_dlq.call_args
        assert call_args[1]["reason"] == "non_retryable_appsflyer_error"

        # Should ack message
        mock_consumer.ack_message.assert_called_once_with("msg-123")


@pytest.mark.asyncio
async def test_retryable_error_increments_attempt_and_reenqueues(
    worker, sample_event, mock_producer, mock_consumer, mock_appsflyer_client
):
    """Test that retryable errors increment attempt and re-enqueue."""
    with patch("app.appsflyer.mapper.AppsFlyerMapper.map_event") as mock_map:
        mock_map.return_value = (MagicMock(), "id123456789")

        # Simulate 500 error (retryable)
        mock_appsflyer_client.send_event.side_effect = AppsFlyerError(
            "Server error",
            status_code=500,
            retryable=True,
        )

        with patch("asyncio.sleep", new=AsyncMock()):  # Skip actual sleep
            await worker._process_event("msg-123", sample_event)

        # Should increment attempt
        assert sample_event.attempt == 1

        # Should re-enqueue
        mock_producer.enqueue.assert_called_once_with(sample_event)

        # Should ack original message
        mock_consumer.ack_message.assert_called_once_with("msg-123")


@pytest.mark.asyncio
async def test_mapping_error_moves_to_dlq(
    worker, sample_event, mock_producer, mock_consumer
):
    """Test that mapping errors move event to DLQ."""
    with patch(
        "app.appsflyer.mapper.AppsFlyerMapper.map_event",
        side_effect=ValueError("Missing required field: appsflyer_id"),
    ):
        await worker._process_event("msg-123", sample_event)

        # Should move to DLQ
        mock_producer.move_to_dlq.assert_called_once()
        call_args = mock_producer.move_to_dlq.call_args
        assert call_args[1]["reason"] == "mapping_error"

        # Should ack message
        mock_consumer.ack_message.assert_called_once_with("msg-123")


@pytest.mark.asyncio
async def test_successful_processing_marks_processed_and_acks(
    worker, sample_event, mock_producer, mock_consumer, mock_appsflyer_client
):
    """Test successful event processing marks as processed and acks."""
    with patch("app.appsflyer.mapper.AppsFlyerMapper.map_event") as mock_map:
        mock_map.return_value = (MagicMock(), "id123456789")

        # Mock successful response
        mock_appsflyer_client.send_event.return_value = MagicMock(status=200)

        await worker._process_event("msg-123", sample_event)

        # Should mark as processed
        mock_producer.mark_processed.assert_called_once_with(sample_event.event_id)

        # Should ack message
        mock_consumer.ack_message.assert_called_once_with("msg-123")

        # Should NOT enqueue or move to DLQ
        mock_producer.enqueue.assert_not_called()
        mock_producer.move_to_dlq.assert_not_called()


@pytest.mark.asyncio
async def test_reclaim_pending_messages_processes_events(worker, mock_consumer):
    """Test that pending messages are reclaimed and processed."""
    pending_fields = {
        "event_type": "purchase",
        "event_id": "pending-event-456",
        "received_at": datetime.now(timezone.utc).isoformat(),
        "payload": '{"appsflyer_id": "device-456", "revenue": "9.99", "currency": "USD"}',
        "attempt": "2",
        "source_meta": "{}",
    }

    mock_consumer.get_pending_messages.return_value = [
        ("pending-msg-1", pending_fields),
    ]

    with patch.object(worker, "_process_event", new=AsyncMock()) as mock_process:
        await worker._reclaim_pending_messages()

        # Should call get_pending_messages
        mock_consumer.get_pending_messages.assert_called_once()

        # Should process the pending event
        mock_process.assert_called_once()
        call_args = mock_process.call_args
        assert call_args[0][0] == "pending-msg-1"
        assert call_args[0][1].event_id == "pending-event-456"


@pytest.mark.asyncio
async def test_retry_after_429_uses_backoff(
    worker, sample_event, mock_producer, mock_consumer, mock_appsflyer_client
):
    """Test that 429 errors trigger retry with backoff."""
    with patch("app.appsflyer.mapper.AppsFlyerMapper.map_event") as mock_map:
        mock_map.return_value = (MagicMock(), "id123456789")

        # Simulate 429 error (rate limit)
        mock_appsflyer_client.send_event.side_effect = AppsFlyerError(
            "Rate limit exceeded",
            status_code=429,
            retryable=True,
        )

        with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await worker._process_event("msg-123", sample_event)

            # Should sleep (backoff)
            mock_sleep.assert_called_once()

            # Should re-enqueue with incremented attempt
            assert sample_event.attempt == 1
            mock_producer.enqueue.assert_called_once()


@pytest.mark.asyncio
async def test_unexpected_error_retries(
    worker, sample_event, mock_producer, mock_consumer, mock_appsflyer_client
):
    """Test that unexpected errors trigger retry."""
    with patch("app.appsflyer.mapper.AppsFlyerMapper.map_event") as mock_map:
        mock_map.return_value = (MagicMock(), "id123456789")

        # Simulate unexpected error
        mock_appsflyer_client.send_event.side_effect = RuntimeError("Unexpected")

        with patch("asyncio.sleep", new=AsyncMock()):
            await worker._process_event("msg-123", sample_event)

        # Should increment attempt and re-enqueue
        assert sample_event.attempt == 1
        mock_producer.enqueue.assert_called_once()
        mock_consumer.ack_message.assert_called_once()
