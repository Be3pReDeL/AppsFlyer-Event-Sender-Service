"""Structured logging configuration using structlog."""

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from app.core.config import get_settings


def mask_sensitive_data(
    logger: logging.Logger,  # noqa: ARG001
    method_name: str,  # noqa: ARG001
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Mask sensitive fields in log output."""
    sensitive_keys = {
        "token",
        "sig",
        "signature",
        "api_key",
        "dev_key",
        "secret",
        "password",
        "authorization",
    }

    def mask_value(key: str, value: Any) -> Any:
        if isinstance(value, str) and any(s in key.lower() for s in sensitive_keys):
            if len(value) > 4:
                return f"{value[:2]}***{value[-2:]}"
            return "***"
        if isinstance(value, dict):
            return {k: mask_value(k, v) for k, v in value.items()}
        return value

    for key in list(event_dict.keys()):
        event_dict[key] = mask_value(key, event_dict[key])

    return event_dict


def add_service_context(
    logger: logging.Logger,  # noqa: ARG001
    method_name: str,  # noqa: ARG001
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Add service context to all log entries."""
    settings = get_settings()
    event_dict["service"] = settings.app_name
    event_dict["environment"] = settings.app_env
    return event_dict


def setup_logging() -> None:
    """Configure structlog for structured JSON logging."""
    settings = get_settings()

    # Shared processors for all log entries
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        add_service_context,
        mask_sensitive_data,
    ]

    if settings.log_format == "json":
        # JSON format for production
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        # Console format for development
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.log_level.upper())

    # Suppress noisy loggers
    for logger_name in ["uvicorn.access", "httpx", "httpcore"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.stdlib.get_logger(name)
