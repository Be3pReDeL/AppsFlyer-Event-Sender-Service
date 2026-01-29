"""Worker entry point for processing events from Redis Streams."""

import asyncio
import signal
import sys

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.models import InternalEvent
from app.queue.consumer import EventConsumer, get_consumer

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

        # Create consumer
        self.consumer = get_consumer(self.redis, self.settings)

        # Ensure consumer group exists
        try:
            await self.consumer.ensure_consumer_group()
        except Exception as e:
            logger.error("consumer_group_setup_failed", error=str(e))
            sys.exit(1)

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
        while self.running:
            try:
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

    async def _process_event(self, message_id: str, event: InternalEvent) -> None:
        """Process a single event.

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

        # TODO: Next stage - send to AppsFlyer
        # For now, just acknowledge immediately (simulating success)
        await asyncio.sleep(0.1)  # Simulate processing

        # Acknowledge message
        await self.consumer.ack_message(message_id)

        logger.info(
            "event_processed",
            message_id=message_id,
            event_id=event.event_id,
            event_type=event.event_type,
        )

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
