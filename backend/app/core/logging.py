"""Structured JSON logging with structlog.

Provides a configured logger that emits JSON lines to stdout (and
optionally a file), with support for request ID correlation, trace
context, and log level control via environment variables.

Usage in application code:

    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("order_created", order_id="abc123", quantity="0.5")
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from app.core.config import settings


def _json_serializer(value: Any, *args: Any) -> str:
    """Fallback JSON serializer for non-stdlib types."""
    import json
    from decimal import Decimal
    from datetime import datetime, date

    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def setup_logging() -> None:
    """Configure structured logging for the entire application.

    Called once at startup (from ``main.py``).  Uses structlog if
    available, otherwise falls back to standard logging with a
    JSON-ish formatter.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    if settings.log_format == "json":
        try:
            import structlog

            timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
            shared_processors: list[Any] = [
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                timestamper,
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer(default=str),
            ]
            structlog.configure(
                processors=shared_processors,
                wrapper_class=structlog.stdlib.BoundLogger,
                logger_factory=structlog.stdlib.LoggerFactory(),
                cache_logger_on_first_use=True,
            )

            # Also configure stdlib logging to use JSON
            stdlib_formatter = structlog.stdlib.ProcessorFormatter(
                processor=structlog.processors.JSONRenderer(default=str),
                foreign_pre_chain=shared_processors[:-1],
            )
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(stdlib_formatter)

            root_logger = logging.getLogger()
            root_logger.handlers.clear()
            root_logger.addHandler(handler)
            root_logger.setLevel(level)

            # File handler (optional)
            if settings.log_file:
                file_handler = logging.FileHandler(settings.log_file)
                file_handler.setFormatter(stdlib_formatter)
                root_logger.addHandler(file_handler)

        except ImportError:
            _setup_stdlib_logging(level)
    else:
        _setup_stdlib_logging(level)

    # Sentry integration (optional)
    if settings.sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.redis import RedisIntegration
            from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                environment=settings.environment,
                traces_sample_rate=0.1,
                send_default_pii=False,
                integrations=[
                    FastApiIntegration(),
                    RedisIntegration(),
                    SqlalchemyIntegration(),
                ],
            )
        except ImportError:
            pass


def _setup_stdlib_logging(level: int) -> None:
    """Fallback: standard logging with a structured format."""
    import json

    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            log_entry = {
                "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if record.exc_info and record.exc_text:
                log_entry["exception"] = record.exc_text
            # Add extra fields
            for key, value in record.__dict__.items():
                if key not in ("name", "msg", "args", "levelname", "levelno",
                               "pathname", "filename", "module", "exc_info",
                               "exc_text", "stack_info", "lineno", "funcName",
                               "created", "msecs", "relativeCreated", "thread",
                               "threadName", "processName", "process", "message"):
                    log_entry[key] = str(value)
            return json.dumps(log_entry, default=_json_serializer)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    if settings.log_file:
        file_handler = logging.FileHandler(settings.log_file)
        file_handler.setFormatter(JsonFormatter())
        root_logger.addHandler(file_handler)


def get_logger(name: str | None = None) -> Any:
    """Return a structured logger.

    When structlog is installed, returns a structlog logger that accepts
    arbitrary kwargs.  Otherwise returns a :class:`StdlibLoggerAdapter`
    that wraps a stdlib logger and converts kwargs to the ``extra`` dict.
    """
    try:
        import structlog
        return structlog.get_logger(name)
    except ImportError:
        return StdlibLoggerAdapter(logging.getLogger(name))


class StdlibLoggerAdapter:
    """Wrapper around stdlib ``logging.Logger`` that accepts arbitrary kwargs.

    Mimics the structlog API so call-sites can use ``logger.info("msg", key=value)``
    without caring whether structlog is installed.
    """

    __slots__ = ("_logger",)

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def _log(self, level: int, msg: str, **kwargs: Any) -> None:
        extra: dict[str, Any] = {}
        for key, value in kwargs.items():
            extra[key] = value
        self._logger.log(level, msg, extra=extra if extra else None)

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, **kwargs)

    def critical(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, msg, **kwargs)

    def exception(self, msg: str, **kwargs: Any) -> None:
        extra: dict[str, Any] = {}
        for key, value in kwargs.items():
            extra[key] = value
        self._logger.exception(msg, extra=extra if extra else None)


def bind_request_context(request_id: str, **kwargs: Any) -> None:
    """Bind request-scoped context to all log entries within the request."""
    try:
        import structlog
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, **kwargs)
    except ImportError:
        pass


def clear_request_context() -> None:
    """Clear request-scoped context (call at the end of each request)."""
    try:
        import structlog
        structlog.contextvars.clear_contextvars()
    except ImportError:
        pass
