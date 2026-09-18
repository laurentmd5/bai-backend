"""
Structured logging configuration for Company Bot.
Uses structlog for JSON-formatted logs with contextual information.
"""

import logging
import sys
import contextvars
from typing import Any, Dict, Optional
from datetime import datetime, timezone

import structlog
from structlog.types import Processor, EventDict

from app.core.config import settings, LogLevel

# Declared at MODULE LEVEL - shared across all logging calls
request_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id",
    default=None
)


def setup_logging() -> None:
    """Initialize logging configuration. Called once at application startup."""
    configure_structlog()


def set_request_id(request_id: str) -> None:
    """Set the current request ID in context."""
    request_id_context.set(request_id)


def get_request_id() -> Optional[str]:
    """Get the current request ID from context."""
    return request_id_context.get()


def add_timestamp(_, __, event_dict: EventDict) -> EventDict:
    """Add ISO 8601 timestamp to log event."""
    event_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
    return event_dict


def add_service_name(_, __, event_dict: EventDict) -> EventDict:
    """Add service name to log event."""
    event_dict["service"] = settings.APP_NAME
    return event_dict


def add_environment(_, __, event_dict: EventDict) -> EventDict:
    """Add environment to log event."""
    event_dict["environment"] = settings.ENVIRONMENT.value
    return event_dict


def add_app_version(_, __, event_dict: EventDict) -> EventDict:
    """Add application version to log event."""
    event_dict["version"] = settings.APP_VERSION
    return event_dict


def mask_sensitive_data(_, __, event_dict: EventDict) -> EventDict:
    """Mask sensitive fields in log events."""
    sensitive_fields = {
        "password", "token", "secret", "api_key", "authorization",
        "access_token", "refresh_token", "csrf_token", "phone_number",
        "email", "message"
    }

    for key in list(event_dict.keys()):
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in sensitive_fields):
            value = event_dict[key]
            if isinstance(value, str) and len(value) > 8:
                event_dict[key] = f"{value[:4]}...{value[-4:]}"
            else:
                event_dict[key] = "***REDACTED***"

    return event_dict


def add_request_id(_, __, event_dict: EventDict) -> EventDict:
    """Extract request ID from context if available."""
    request_id = request_id_context.get()
    if request_id:
        event_dict["request_id"] = request_id
    return event_dict


def configure_structlog() -> None:
    """Configure structlog for structured JSON logging."""
    log_level = getattr(logging, settings.LOG_LEVEL.value)

    shared_processors: list[Processor] = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_service_name,
        add_environment,
        add_app_version,
        add_request_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.LOG_FORMAT == "json":
        structlog.configure(
            processors=shared_processors + [
                mask_sensitive_data,
                structlog.processors.JSONRenderer()
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        structlog.configure(
            processors=shared_processors + [
                structlog.dev.ConsoleRenderer(colors=True)
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )


def get_logger(name: Optional[str] = None) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


# Initialize structlog on module import
configure_structlog()

# Default logger instance
logger = get_logger(__name__)


class RequestLogger:
    """Context manager for logging request lifecycle."""

    def __init__(self, request_id: str, method: str, path: str, client_ip: str):
        self.request_id = request_id
        self.method = method
        self.path = path
        self.client_ip = client_ip
        self.start_time: Optional[datetime] = None
        self.logger = get_logger("api.request")

    def __enter__(self):
        self.start_time = datetime.now(timezone.utc)
        self.logger.info(
            "request_started",
            request_id=self.request_id,
            method=self.method,
            path=self.path,
            client_ip=self.client_ip,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (datetime.now(timezone.utc) - self.start_time).total_seconds() * 1000

        log_data = {
            "request_id": self.request_id,
            "method": self.method,
            "path": self.path,
            "client_ip": self.client_ip,
            "duration_ms": round(duration_ms, 2),
        }

        if exc_type:
            log_data["error"] = str(exc_val)
            log_data["error_type"] = exc_type.__name__
            self.logger.error("request_failed", **log_data)
        else:
            self.logger.info("request_completed", **log_data)
        set_request_id(None)
