"""Structured logging configuration.

Emits JSON log lines so logs are machine-parseable from day one.
Request-scoped fields (request_id, user_id, tenant_id) are injected into
every log record automatically via RequestContextFilter, reading from
app/core/request_context.py's contextvars — see ADR-014. Callers never pass
these explicitly; a plain `logger.info("something happened")` anywhere
during a request already carries full correlation context.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.request_context import get_organization_id, get_request_id, get_user_id


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        request_id = get_request_id()
        user_id = get_user_id()
        organization_id = get_organization_id()
        if request_id is not None:
            record.request_id = request_id
        if user_id is not None:
            record.user_id = user_id
        if organization_id is not None:
            record.organization_id = organization_id
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Never emit secrets: known-sensitive attribute names are dropped if present.
        sensitive_keys = {"password", "api_key", "token", "secret"}
        extra = {
            k: v
            for k, v in record.__dict__.items()
            if k
            not in (
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "taskName",
            )
            and k.lower() not in sensitive_keys
        }
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestContextFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
