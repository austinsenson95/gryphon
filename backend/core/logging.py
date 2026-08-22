"""Structured logging.

Stdlib logging with a JSON-lines formatter. Level comes from the LOG_LEVEL
environment variable (default INFO). Secrets must never be logged — never pass
API keys/tokens into log records.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

_CONFIGURED = False


_RESERVED = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "taskName", "message", "asctime",
    }
)


class JsonFormatter(logging.Formatter):
    """Minimal JSON-ish structured formatter."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Merge structured extras (anything passed via extra={...}).
        for key, value in record.__dict__.items():
            if key in _RESERVED:
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)
        return json.dumps(payload, default=str)


def setup_logging(level: str | None = None) -> None:
    """Configure root logging once."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    resolved = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(resolved)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Get a named logger, ensuring base configuration exists."""
    setup_logging()
    return logging.getLogger(name)
