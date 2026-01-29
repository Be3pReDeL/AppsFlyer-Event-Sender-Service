"""Tests for bug fixes: TOCTOU race condition and consistent backoff."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.core.exceptions import AppsFlyerError
from app.core.models import InternalEvent
from app.queue.producer import EventProducer
from app.worker.run import Worker


@pytest.mark.asyncio
async def test_atomic_deduplication_prevents_race_condition() -> None:
    """Test that check_and_mark_if_new prevents TOCTOU race condition."""
    mock_redis = AsyncMock()
    settings = Settings(dedup_ttl_seconds=3600)
    producer = EventProducer(mock_redis, settings)

    # First call - key doesn't exist, SET NX succeeds
    mock_redis.set.return_value = True
    is_new_1 = await producer.check_and_mark_if_new("event_123")
    assert is_new_1 is True
    mock_redis.set.assert_called_once_with(
        "dedup:event_123",
        "1",
        nx=True,
        ex=3600,
    )

    # Second call (concurrent request with same event_id) - key exists, SET NX fails
    mock_redis.reset_mock()
    mock_redis.set.return_value = False  # Key already exists
    is_new_2 = await producer.check_and_mark_if_new("event_123")
    assert is_new_2 is False
    mock_redis.set.assert_called_once_with(
        "dedup:event_123",
        "1",
        nx=True,
        ex=3600,
    )

    # Verify that the operation is atomic (single Redis call, no TOCTOU window)


@pytest.mark.asyncio
async def test_atomic_deduplication_error_handling() -> None:
    """Test that check_and_mark_if_new handles Redis errors gracefully."""
    mock_redis = AsyncMock()
    settings = Settings(dedup_ttl_seconds=3600)
    producer = EventProducer(mock_redis, settings)

    # Simulate Redis error
    mock_redis.set.side_effect = Exception("Redis connection failed")

    # Should return True (assume new) to avoid false blocking
    is_new = await producer.check_and_mark_if_new("event_456")
    assert is_new is True


@pytest.mark.asyncio
async def test_consistent_backoff_for_appsflyer_error() -> None:
    """Test that AppsFlyerError uses consistent backoff calculation."""
    mock_redis = AsyncMock()
    mock_consumer = AsyncMock()
    mock_producer = AsyncMock()
    mock_appsflyer_client = AsyncMock()

    settings = Settings(
        backoff_base_seconds=1.0,
        backoff_max_seconds=60.0,
    )

    worker = Worker()
    worker.settings = settings
    worker.redis = mock_redis
    worker.consumer = mock_consumer
    worker.producer = mock_producer
    worker.appsflyer_client = mock_appsflyer_client
    worker.running = True

    event = InternalEvent(
        event_type="registration",
        event_id="test_evt_123",
        received_at=datetime.now(timezone.utc),
        payload={"appsflyer_id": "device-123"},
        attempt=0,
        source_meta={},
    )

    with patch("app.appsflyer.mapper.AppsFlyerMapper.map_event") as mock_map:
        mock_map.return_value = (MagicMock(), "id123456789")

        # Simulate 500 error (retryable)
        mock_appsflyer_client.send_event.side_effect = AppsFlyerError(
            "Server error",
            status_code=500,
            retryable=True,
        )

        with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await worker._process_event("msg-123", event)

            # Verify attempt was incremented BEFORE backoff calculation
            assert event.attempt == 1

            # Verify backoff was calculated with incremented attempt (attempt=1)
            # For attempt=1: delay = 1.0 * (2^1) = 2.0s (before jitter)
            # With jitter (±25%): 1.5s to 2.5s
            actual_backoff = mock_sleep.call_args[0][0]
            assert 1.5 <= actual_backoff <= 2.5

            # Verify re-enqueue was called
            mock_producer.enqueue.assert_called_once()
            enqueued_event = mock_producer.enqueue.call_args[0][0]
            assert enqueued_event.attempt == 1


@pytest.mark.asyncio
async def test_consistent_backoff_for_unexpected_error() -> None:
    """Test that unexpected errors use same backoff calculation as AppsFlyerError."""
    mock_redis = AsyncMock()
    mock_consumer = AsyncMock()
    mock_producer = AsyncMock()
    mock_appsflyer_client = AsyncMock()

    settings = Settings(
        backoff_base_seconds=1.0,
        backoff_max_seconds=60.0,
    )

    worker = Worker()
    worker.settings = settings
    worker.redis = mock_redis
    worker.consumer = mock_consumer
    worker.producer = mock_producer
    worker.appsflyer_client = mock_appsflyer_client
    worker.running = True

    event = InternalEvent(
        event_type="registration",
        event_id="test_evt_456",
        received_at=datetime.now(timezone.utc),
        payload={"appsflyer_id": "device-456"},
        attempt=0,
        source_meta={},
    )

    with patch("app.appsflyer.mapper.AppsFlyerMapper.map_event") as mock_map:
        mock_map.return_value = (MagicMock(), "id123456789")

        # Simulate unexpected error
        mock_appsflyer_client.send_event.side_effect = RuntimeError("Unexpected")

        with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await worker._process_event("msg-456", event)

            # Verify attempt was incremented
            assert event.attempt == 1

            # Verify backoff was calculated with incremented attempt (attempt=1)
            # For attempt=1: delay = 1.0 * (2^1) = 2.0s (before jitter)
            # With jitter (±25%): 1.5s to 2.5s
            actual_backoff = mock_sleep.call_args[0][0]
            assert 1.5 <= actual_backoff <= 2.5

            # Verify backoff is CONSISTENT between AppsFlyerError and unexpected errors


@pytest.mark.asyncio
async def test_backoff_sequence_is_consistent() -> None:
    """Test that backoff sequence is consistent regardless of error type."""
    settings = Settings(
        backoff_base_seconds=1.0,
        backoff_max_seconds=60.0,
    )
    worker = Worker()
    worker.settings = settings

    # Test backoff for attempts 1, 2, 3
    # After first failure: attempt becomes 1, backoff ~2s
    # After second failure: attempt becomes 2, backoff ~4s
    # After third failure: attempt becomes 3, backoff ~8s

    backoff_1 = worker._calculate_backoff(1)
    backoff_2 = worker._calculate_backoff(2)
    backoff_3 = worker._calculate_backoff(3)

    # Verify exponential progression (accounting for jitter)
    assert 1.5 <= backoff_1 <= 2.5  # 2.0 ± 25%
    assert 3.0 <= backoff_2 <= 5.0  # 4.0 ± 25%
    assert 6.0 <= backoff_3 <= 10.0  # 8.0 ± 25%
