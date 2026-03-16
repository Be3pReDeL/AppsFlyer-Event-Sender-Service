"""Worker entry point for processing events from Redis Streams."""

import asyncio
import random
import signal
import sys

import redis.asyncio as aioredis

from app.appsflyer.client import AppsFlyerClient, get_client
from app.appsflyer.dev_key_repository import DevKeyRepository
from app.appsflyer.mapper import AppsFlyerMapper
from app.core.config import get_settings
from app.core.exceptions import AppsFlyerError
from app.core.logging import get_logger, setup_logging
from app.core.metrics import record_processed, record_retry
from app.core.models import InternalEvent
from app.queue.consumer import EventConsumer, get_consumer
from app.queue.producer import EventProducer, get_producer

# Initialize logging
setup_logging()

logger = get_logger(__name__)


class Worker:
    """Event processing worker using Redis Streams consumer group."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.running = False
        self._shutdown_event = asyncio.Event()
        self.redis: aioredis.Redis | None = None
        self.consumer: EventConsumer | None = None
        self.producer: EventProducer | None = None
        self.appsflyer_client: AppsFlyerClient | None = None
        self.dev_key_repository: DevKeyRepository | None = None
        self._last_pending_check = 0.0

    async def start(self) -> None:
        """Start the worker."""
        self.running = True

        # Connect to Redis
        try:
            self.redis = aioredis.from_url(
                self.settings.redis_url,
                decode_responses=True,
                max_connections=20,
            )
            await self.redis.ping()
            logger.info("redis_connected")
        except Exception as e:
            logger.error("redis_connection_failed", error=str(e))
            sys.exit(1)

        # Create consumer and producer
        self.consumer = get_consumer(self.redis, self.settings)
        self.producer = get_producer(self.redis, self.settings)

        # Ensure consumer group exists
        try:
            await self.consumer.ensure_consumer_group()
        except Exception as e:
            logger.error("consumer_group_setup_failed", error=str(e))
            sys.exit(1)

        # Create AppsFlyer client
        self.appsflyer_client = get_client(self.settings)
        self.dev_key_repository = DevKeyRepository(
            database_url=self.settings.appsflyer_dev_key_database_url,
            sqlite_db_path=self.settings.appsflyer_dev_key_db_path,
        )

        logger.info(
            "worker_started",
            consumer_group=self.settings.worker_consumer_group,
            consumer_name=self.consumer.consumer_name,
            stream=self.settings.stream_main,
        )

        # Start processing loop
        await self._process_loop()

    async def _process_loop(self) -> None:
        """Main processing loop."""
        import time

        while self.running:
            try:
                # Periodically reclaim pending messages (every 30 seconds)
                now = time.time()
                if now - self._last_pending_check > 30:
                    await self._reclaim_pending_messages()
                    self._last_pending_check = now

                # Read events from stream
                events = await self.consumer.read_events(count=10, block_ms=5000)

                if not events:
                    # No events, continue waiting
                    continue

                # Process each event
                for message_id, event in events:
                    try:
                        await self._process_event(message_id, event)
                    except Exception as e:
                        logger.exception(
                            "event_processing_failed",
                            message_id=message_id,
                            event_id=event.event_id,
                            error=str(e),
                        )
                        # Don't ack - will be retried or reclaimed

            except Exception as e:
                if self.running:
                    logger.error("processing_loop_error", error=str(e))
                    # Brief backoff on loop errors
                    await asyncio.sleep(1)

        logger.info("processing_loop_stopped")

    async def _reclaim_pending_messages(self) -> None:
        """Reclaim and process pending messages that have been idle too long."""
        try:
            pending = await self.consumer.get_pending_messages(
                min_idle_ms=self.settings.pending_claim_ms
            )

            if pending:
                logger.info(
                    "reclaiming_pending_messages",
                    count=len(pending),
                    min_idle_ms=self.settings.pending_claim_ms,
                )

                for message_id, fields in pending:
                    try:
                        event = InternalEvent.from_stream_fields(fields)
                        await self._process_event(str(message_id), event)
                    except Exception as e:
                        logger.error(
                            "pending_message_processing_failed",
                            message_id=message_id,
                            error=str(e),
                        )
                        # Will be reclaimed again or moved to DLQ

        except Exception as e:
            logger.error("pending_reclaim_failed", error=str(e))

    async def _process_event(self, message_id: str, event: InternalEvent) -> None:
        """Process a single event with retry logic.

        Args:
            message_id: Redis Stream message ID
            event: Internal event to process
        """
        logger.info(
            "processing_event",
            message_id=message_id,
            event_id=event.event_id,
            event_type=event.event_type,
            attempt=event.attempt,
        )

        # Check if max attempts exceeded
        if event.attempt >= self.settings.max_attempts:
            logger.error(
                "max_attempts_exceeded",
                event_id=event.event_id,
                attempt=event.attempt,
                max_attempts=self.settings.max_attempts,
            )
            await self.producer.move_to_dlq(
                event=event,
                reason="max_attempts_exceeded",
                last_error=f"Failed after {event.attempt} attempts",
            )
            await self.consumer.ack_message(message_id)
            return

        try:
            # Map internal event to AppsFlyer request
            af_request, app_id = AppsFlyerMapper.map_event(event)
            request_dev_key = event.payload.get("dev_key")
            resolved_dev_key = await self._resolve_dev_key(
                app_id=app_id,
                request_dev_key=request_dev_key if isinstance(request_dev_key, str) else None,
            )

            # Send to AppsFlyer
            af_response = await self.appsflyer_client.send_event(
                af_request,
                event.event_id,
                app_id=app_id,
                dev_key=resolved_dev_key,
            )

            logger.info(
                "appsflyer_send_success",
                event_id=event.event_id,
                message_id=message_id,
                af_status=af_response.status,
            )

            # Mark as processed for deduplication
            await self.producer.mark_processed(event.event_id)

            # Acknowledge message on success
            await self.consumer.ack_message(message_id)

            logger.info(
                "event_processed",
                message_id=message_id,
                event_id=event.event_id,
                event_type=event.event_type,
            )

            # Record success metric
            record_processed(event.event_type, "success")

        except AppsFlyerError as e:
            logger.warning(
                "appsflyer_send_failed",
                event_id=event.event_id,
                message_id=message_id,
                error=str(e),
                retryable=e.retryable,
                status_code=e.status_code,
                attempt=event.attempt,
            )

            if not e.retryable:
                # Non-retryable error (4xx) - move to DLQ immediately
                logger.error(
                    "non_retryable_error",
                    event_id=event.event_id,
                    status_code=e.status_code,
                )
                await self.producer.move_to_dlq(
                    event=event,
                    reason="non_retryable_appsflyer_error",
                    last_error=str(e),
                )
                await self.consumer.ack_message(message_id)
                return

            # Retryable error - increment attempt, calculate backoff and wait
            event.attempt += 1
            backoff_delay = self._calculate_backoff(event.attempt)
            logger.info(
                "retrying_event",
                event_id=event.event_id,
                attempt=event.attempt,
                backoff_seconds=backoff_delay,
            )

            # Record retry metric
            record_retry(event.event_type)

            await asyncio.sleep(backoff_delay)

            # Re-enqueue with incremented attempt
            await self.producer.enqueue(event)

            # Ack original message (new one will be processed in next iteration)
            await self.consumer.ack_message(message_id)

        except ValueError as e:
            # Mapping error (missing required fields) - non-retryable
            logger.error(
                "event_mapping_failed",
                event_id=event.event_id,
                message_id=message_id,
                error=str(e),
            )
            await self.producer.move_to_dlq(
                event=event,
                reason="mapping_error",
                last_error=str(e),
            )
            await self.consumer.ack_message(message_id)

        except Exception as e:
            # Unexpected error - treat as retryable but with caution
            logger.exception(
                "unexpected_error",
                event_id=event.event_id,
                message_id=message_id,
                error=str(e),
            )

            # Increment attempt and re-enqueue
            event.attempt += 1
            backoff_delay = self._calculate_backoff(event.attempt)
            await asyncio.sleep(backoff_delay)
            await self.producer.enqueue(event)
            await self.consumer.ack_message(message_id)

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff with jitter.

        Args:
            attempt: Current attempt number (0-based)

        Returns:
            Backoff delay in seconds
        """
        # Exponential backoff: base * (2 ^ attempt)
        delay = self.settings.backoff_base_seconds * (2**attempt)

        # Cap at max
        delay = min(delay, self.settings.backoff_max_seconds)

        # Add jitter (±25%)
        jitter_range = delay * 0.25
        jitter = random.uniform(-jitter_range, jitter_range)
        delay += jitter

        # Ensure non-negative
        return max(0.1, delay)

    async def _resolve_dev_key(
        self,
        app_id: str | None,
        request_dev_key: str | None,
    ) -> str | None:
        """Resolve dev key by priority: request param -> DB mapping -> env default."""
        if request_dev_key and request_dev_key.strip():
            return request_dev_key.strip()

        if not app_id:
            # Let AppsFlyer client apply env fallback and validation.
            return None

        if self.dev_key_repository is None:
            self.dev_key_repository = DevKeyRepository(
                database_url=self.settings.appsflyer_dev_key_database_url,
                sqlite_db_path=self.settings.appsflyer_dev_key_db_path,
            )

        try:
            mapped_dev_key = await self.dev_key_repository.get_dev_key(app_id.strip())
            if mapped_dev_key:
                return mapped_dev_key
        except Exception as e:
            # Continue with env fallback if mapping DB is temporarily unavailable.
            logger.error("dev_key_lookup_failed", app_id=app_id, error=str(e))

        return None

    async def stop(self) -> None:
        """Stop the worker gracefully."""
        logger.info("worker_stopping")
        self.running = False
        self._shutdown_event.set()

        # Close Redis connection
        if self.redis:
            await self.redis.aclose()
            logger.info("redis_disconnected")


async def main() -> None:
    """Main worker entry point."""
    worker = Worker()

    # Setup signal handlers
    loop = asyncio.get_event_loop()

    def shutdown_handler() -> None:
        logger.info("shutdown_signal_received")
        asyncio.create_task(worker.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_handler)

    try:
        await worker.start()
    except Exception as e:
        logger.exception("worker_error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
