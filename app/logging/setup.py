"""Logging helpers that avoid leaking secrets and produce structured output."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.config.settings import Settings

_STANDARD_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}

_SECRET_FIELD_HINTS = ("password", "secret", "token", "api_key", "api_hash", "session", "otp")


def redact_if_sensitive(key: str, value: Any) -> Any:
    """Redact values whose field names indicate credentials or session data."""

    if any(hint in key.lower() for hint in _SECRET_FIELD_HINTS):
        return "***REDACTED***"
    return value


class JsonFormatter(logging.Formatter):
    """Small JSON formatter for machine-readable application logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_FIELDS or key.startswith("_"):
                continue
            payload[key] = redact_if_sensitive(key, value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(settings: Settings) -> None:
    """Configure root logging once for CLI commands and workers."""

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(settings.log_level)

    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="[%(levelname)s] %(message)s",
            )
        )

    root_logger.addHandler(handler)
