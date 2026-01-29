"""Worker entry point for processing events from Redis Streams."""

import asyncio
import signal
import sys

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging

# Initialize logging
setup_logging()

logger = get_logger(__name__)


class Worker:
    """Event processing worker using Redis Streams consumer group."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.running = False
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the worker."""
        self.running = True
        logger.info(
            "worker_started",
            consumer_group=self.settings.worker_consumer_group,
            stream=self.settings.stream_main,
        )

        # Wait for shutdown signal
        await self._shutdown_event.wait()

        logger.info("worker_stopped")

    async def stop(self) -> None:
        """Stop the worker gracefully."""
        logger.info("worker_stopping")
        self.running = False
        self._shutdown_event.set()


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
