import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


def get_utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(dt: datetime | None = None) -> str:
    return (dt or get_utcnow()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
        force=True,
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, *, event: str, level: int = logging.INFO, **fields: Any) -> None:
    parts = [f"{key}={value!r}" for key, value in fields.items()]
    logger.log(level, "event=%s %s", event, " ".join(parts))


def env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}