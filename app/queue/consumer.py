"""Redis Streams consumer for processing events."""

from typing import Any

import redis.asyncio as aioredis

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.models import InternalEvent

logger = get_logger(__name__)


class EventConsumer:
    """Consumer for reading events from Redis Streams using Consumer Groups."""

    def __init__(self, redis_client: aioredis.Redis, settings: Settings) -> None:
        self.redis = redis_client
        self.settings = settings
        self.consumer_name = settings.worker_consumer_name or f"worker-{id(self)}"

    async def ensure_consumer_group(self) -> None:
        """Ensure consumer group exists for the stream."""
        try:
            await self.redis.xgroup_create(
                name=self.settings.stream_main,
                groupname=self.settings.worker_consumer_group,
                id="0",
                mkstream=True,
            )
            logger.info(
                "consumer_group_created",
                stream=self.settings.stream_main,
                group=self.settings.worker_consumer_group,
            )
        except Exception as e:
            # Group might already exist - this is OK
            if "BUSYGROUP" in str(e):
                logger.debug(
                    "consumer_group_exists",
                    stream=self.settings.stream_main,
                    group=self.settings.worker_consumer_group,
                )
            else:
                logger.error("consumer_group_creation_failed", error=str(e))
                raise

    async def read_events(
        self,
        count: int = 10,
        block_ms: int = 5000,
    ) -> list[tuple[str, InternalEvent]]:
        """Read events from stream using consumer group.

        Args:
            count: Maximum number of messages to read
            block_ms: Time to block waiting for messages (milliseconds)

        Returns:
            List of (message_id, InternalEvent) tuples
        """
        try:
            # Read from consumer group
            response = await self.redis.xreadgroup(
                groupname=self.settings.worker_consumer_group,
                consumername=self.consumer_name,
                streams={self.settings.stream_main: ">"},
                count=count,
                block=block_ms,
            )

            events: list[tuple[str, InternalEvent]] = []

            if not response:
                return events

            # Parse response: [[stream_name, [(message_id, fields), ...]]]
            for _stream_name, messages in response:
                for message_id, fields in messages:
                    try:
                        event = InternalEvent.from_stream_fields(fields)
                        events.append((str(message_id), event))
                        logger.debug(
                            "event_read",
                            message_id=message_id,
                            event_id=event.event_id,
                            event_type=event.event_type,
                        )
                    except Exception as e:
                        logger.error(
                            "event_parse_failed",
                            message_id=message_id,
                            error=str(e),
                            fields=fields,
                        )
                        # Skip malformed messages
                        continue

            return events

        except Exception as e:
            logger.error("read_events_failed", error=str(e))
            # Return empty list on error to allow retry
            return []

    async def ack_message(self, message_id: str) -> None:
        """Acknowledge successful processing of a message.

        Args:
            message_id: Redis Stream message ID to acknowledge
        """
        try:
            await self.redis.xack(
                self.settings.stream_main,
                self.settings.worker_consumer_group,
                message_id,
            )
            logger.debug("message_acked", message_id=message_id)
        except Exception as e:
            logger.error(
                "ack_failed",
                message_id=message_id,
                error=str(e),
            )
            # Non-critical - message will be reclaimed

    async def get_pending_messages(self, min_idle_ms: int) -> list[tuple[str, dict[str, Any]]]:
        """Get pending messages that have been idle for too long.

        Args:
            min_idle_ms: Minimum idle time in milliseconds

        Returns:
            List of (message_id, fields) tuples
        """
        try:
            # Use xautoclaim to reclaim pending messages
            result = await self.redis.xautoclaim(
                name=self.settings.stream_main,
                groupname=self.settings.worker_consumer_group,
                consumername=self.consumer_name,
                min_idle_time=min_idle_ms,
                start_id="0-0",
                count=100,
            )

            # xautoclaim returns: (next_start_id, claimed_messages, deleted_ids)
            if isinstance(result, tuple) and len(result) >= 2:
                claimed_messages = result[1]
                if claimed_messages:
                    logger.info(
                        "pending_messages_claimed",
                        count=len(claimed_messages),
                        min_idle_ms=min_idle_ms,
                    )
                    return claimed_messages
            return []

        except Exception as e:
            logger.error("pending_claim_failed", error=str(e))
            return []


def get_consumer(redis: aioredis.Redis, settings: Settings) -> EventConsumer:
    """Factory function to create EventConsumer instance."""
    return EventConsumer(redis, settings)
