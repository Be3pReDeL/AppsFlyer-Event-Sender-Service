"""Redis Streams producer for enqueueing events."""


import redis.asyncio as aioredis

from app.core.config import Settings
from app.core.exceptions import QueueError
from app.core.logging import get_logger
from app.core.models import InternalEvent

logger = get_logger(__name__)


class EventProducer:
    """Producer for adding events to Redis Streams."""

    def __init__(self, redis_client: aioredis.Redis, settings: Settings) -> None:
        self.redis = redis_client
        self.settings = settings

    async def enqueue(self, event: InternalEvent) -> str:
        """Enqueue event to main stream.

        Args:
            event: Internal event to enqueue

        Returns:
            Redis Stream message ID

        Raises:
            QueueError: If enqueue fails
        """
        try:
            # Convert event to stream fields
            fields = event.to_stream_fields()

            # Add to stream
            message_id = await self.redis.xadd(
                name=self.settings.stream_main,
                fields=fields,
            )

            logger.info(
                "event_enqueued",
                event_id=event.event_id,
                event_type=event.event_type,
                stream=self.settings.stream_main,
                message_id=message_id,
            )

            return str(message_id)

        except Exception as e:
            logger.error(
                "enqueue_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(e),
            )
            raise QueueError(f"Failed to enqueue event: {e}") from e

    async def check_duplicate(self, event_id: str) -> bool:
        """Check if event_id already exists in deduplication cache.

        Args:
            event_id: Event identifier to check

        Returns:
            True if event is a duplicate, False otherwise
        """
        try:
            dedup_key = f"dedup:{event_id}"
            exists = await self.redis.exists(dedup_key)
            return bool(exists)
        except Exception as e:
            logger.error(
                "dedup_check_failed",
                event_id=event_id,
                error=str(e),
            )
            # On error, assume not duplicate to avoid false blocking
            return False

    async def check_and_mark_if_new(self, event_id: str) -> bool:
        """Atomically check if event is new and mark it as processed if so.

        Uses Redis SET NX to avoid TOCTOU race condition.

        Args:
            event_id: Event identifier to check and mark

        Returns:
            True if event is NEW (was successfully marked), False if duplicate
        """
        try:
            dedup_key = f"dedup:{event_id}"
            # SET NX with expiry - returns True if key was set, False if already exists
            was_set = await self.redis.set(
                dedup_key,
                "1",
                nx=True,  # Only set if not exists (atomic check-and-set)
                ex=self.settings.dedup_ttl_seconds,
            )
            return bool(was_set)
        except Exception as e:
            logger.error(
                "dedup_check_and_mark_failed",
                event_id=event_id,
                error=str(e),
            )
            # On error, assume event is new to avoid false blocking
            return True

    async def mark_processed(self, event_id: str) -> None:
        """Mark event as processed in deduplication cache.

        Args:
            event_id: Event identifier to mark
        """
        try:
            dedup_key = f"dedup:{event_id}"
            await self.redis.setex(
                dedup_key,
                self.settings.dedup_ttl_seconds,
                "1",
            )
            logger.debug("event_marked_processed", event_id=event_id)
        except Exception as e:
            logger.error(
                "dedup_mark_failed",
                event_id=event_id,
                error=str(e),
            )
            # Non-critical error, don't raise

    async def move_to_dlq(
        self,
        event: InternalEvent,
        reason: str,
        last_error: str | None = None,
    ) -> None:
        """Move event to dead letter queue.

        Args:
            event: Event to move to DLQ
            reason: Reason for moving to DLQ
            last_error: Last error message
        """
        try:
            fields = event.to_stream_fields()
            fields["dlq_reason"] = reason
            if last_error:
                fields["last_error"] = last_error[:500]  # Limit error length

            message_id = await self.redis.xadd(
                name=self.settings.stream_dlq,
                fields=fields,
            )

            logger.warning(
                "event_moved_to_dlq",
                event_id=event.event_id,
                event_type=event.event_type,
                reason=reason,
                attempt=event.attempt,
                dlq_message_id=message_id,
            )

        except Exception as e:
            logger.error(
                "dlq_move_failed",
                event_id=event.event_id,
                error=str(e),
            )
            # Critical: DLQ write failed, but we can't do much here
            raise QueueError(f"Failed to move event to DLQ: {e}") from e


def get_producer(redis: aioredis.Redis, settings: Settings) -> EventProducer:
    """Factory function to create EventProducer instance."""
    return EventProducer(redis, settings)
