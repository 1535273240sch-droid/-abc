"""Pluggable versioned domain event bus.

Phase 1 provides an in-memory implementation. The interface is kept stable so
a reliable message system can be slotted in later (ARCHITECTURE.md section 5:
"第一阶段实现可插拔的事件总线，开发环境允许内存/本地实现").
"""

import logging
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_event_id(kind: str) -> str:
    return f"evt-{kind}-{uuid.uuid4().hex[:12]}"


def event_type(module: str, name: str, version: int = 1) -> str:
    """Versioned event type, e.g. ``market.ticker.v1`` (ARCHITECTURE.md 6.1)."""
    return f"{module}.{name}.v{version}"


@dataclass(frozen=True)
class DomainEvent:
    event_type: str
    event_id: str
    event_time: datetime
    version: int
    actor: str = "system"
    resource_type: str = ""
    resource_id: str = ""
    trace_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


EventHandler = Callable[[DomainEvent], Any]


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._published: dict[str, int] = {}

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        self._subscribers.setdefault("*", []).append(handler)

    def publish(self, event: DomainEvent) -> None:
        self._published[event.event_type] = self._published.get(event.event_type, 0) + 1
        handlers = list(self._subscribers.get(event.event_type, [])) + list(self._subscribers.get("*", []))
        if not handlers:
            return
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:  # noqa: BLE001
                logger.error("Event handler failed for %s: %s", event.event_type, e)

    def counts(self) -> dict[str, int]:
        return dict(self._published)


    def health(self) -> dict[str, Any]:
        return {"backend": "memory", "ready": True, "stream": None, "last_error": None}


class RedisEventBus(EventBus):
    """Redis Streams-backed event bus with consumer groups and DLQ.

    Provides at-least-once delivery semantics via consumer groups:
    - ``publish`` writes to the stream (fire-and-forget for local handlers).
    - ``consume`` reads new messages via XREADGROUP.
    - ``ack`` acknowledges successful processing (removes from PEL).
    - ``reject`` moves a message to the Dead Letter Queue and acknowledges.
    - ``claim_stale`` recovers messages left unacked by crashed consumers.
    """

    DEFAULT_GROUP = "quant-consumers"
    DEFAULT_DLQ = "quant.domain.events.dlq"

    def __init__(self, url: str, stream: str, group: str | None = None, dlq_stream: str | None = None):
        super().__init__()
        self.stream = stream
        self.group = group or self.DEFAULT_GROUP
        self.dlq_stream = dlq_stream or self.DEFAULT_DLQ
        self.last_error: str | None = None
        self._client = None
        try:
            import redis

            self._client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3)
            self._client.ping()
            self._ensure_group()
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)[:500]
            self._client = None

    def _ensure_group(self) -> None:
        """Create the consumer group if it does not already exist."""
        if self._client is None:
            return
        try:
            self._client.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except Exception as exc:  # noqa: BLE001
            # BUSYGROUP means the group already exists — expected on restart
            if "BUSYGROUP" not in str(exc):
                logger.debug("xgroup_create returned %s (stream=%s, group=%s)", exc, self.stream, self.group)

    def publish(self, event: DomainEvent) -> None:
        if self._client is not None:
            try:
                self._client.xadd(
                    self.stream,
                    {
                        "event_type": event.event_type,
                        "event_id": event.event_id,
                        "event_time": event.event_time.isoformat(),
                        "version": str(event.version),
                        "actor": event.actor,
                        "resource_type": event.resource_type,
                        "resource_id": event.resource_id,
                        "trace_id": event.trace_id or "",
                        "payload": json.dumps(event.payload, ensure_ascii=False, default=str),
                    },
                    maxlen=100000,
                    approximate=True,
                )
                self.last_error = None
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)[:500]
                logger.error("Redis event publish failed for %s: %s", event.event_type, self.last_error)
        super().publish(event)

    def consume(self, consumer: str, count: int = 100, block_ms: int = 5000) -> list[dict[str, Any]]:
        """Read events from the stream as a consumer group member.

        Returns a list of message dicts.  Each dict includes the
        ``entry_id`` plus all stream fields.  The caller must call
        :meth:`ack` or :meth:`reject` for each message.
        """
        if self._client is None:
            return []
        try:
            results = self._client.xreadgroup(
                self.group, consumer,
                {self.stream: ">"},
                count=count, block=block_ms,
            )
            messages: list[dict[str, Any]] = []
            for _stream, entries in results:
                for entry_id, fields in entries:
                    msg = {"entry_id": entry_id}
                    msg.update(fields)
                    messages.append(msg)
            return messages
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)[:500]
            logger.error("Redis consume failed: %s", self.last_error)
            return []

    def ack(self, entry_id: str) -> bool:
        """Acknowledge that *entry_id* has been processed successfully."""
        if self._client is None:
            return False
        try:
            self._client.xack(self.stream, self.group, entry_id)
            return True
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)[:500]
            logger.error("Redis ack failed for %s: %s", entry_id, self.last_error)
            return False

    def reject(self, entry_id: str, reason: str | None = None) -> bool:
        """Move *entry_id* to the Dead Letter Queue and acknowledge it.

        The original message fields are preserved; ``_dlq_reason``,
        ``_dlq_original_stream``, ``_dlq_original_id`` and
        ``_dlq_timestamp`` are added for traceability.
        """
        if self._client is None:
            return False
        try:
            messages = self._client.xrange(self.stream, entry_id, entry_id, count=1)
            if messages:
                _, fields = messages[0]
                dlq_fields = dict(fields)
                dlq_fields["_dlq_reason"] = reason or "rejected"
                dlq_fields["_dlq_original_stream"] = self.stream
                dlq_fields["_dlq_original_id"] = entry_id
                dlq_fields["_dlq_timestamp"] = now_utc().isoformat()
                self._client.xadd(self.dlq_stream, dlq_fields, maxlen=10000, approximate=True)
            self._client.xack(self.stream, self.group, entry_id)
            return True
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)[:500]
            logger.error("Redis reject failed for %s: %s", entry_id, self.last_error)
            return False

    def pending_entries(self, count: int = 100) -> list[dict[str, Any]]:
        """Return entries in the Pending Entry List (PEL).

        PEL entries are messages delivered to a consumer but never
        acknowledged, typically due to a consumer crash.
        """
        if self._client is None:
            return []
        try:
            raw = self._client.xpending_range(self.stream, self.group, count=count)
            return [
                {
                    "entry_id": r.get("message_id", r.get("entry_id", "")),
                    "consumer": r.get("consumer", ""),
                    "time_since_delivered_ms": r.get("time_since_delivered", 0),
                    "delivery_count": r.get("times_delivered", r.get("delivery_count", 1)),
                }
                for r in raw
            ]
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)[:500]
            return []

    def claim_stale(self, consumer: str, min_idle_ms: int = 60000, count: int = 10) -> list[dict[str, Any]]:
        """Claim stale messages from the PEL.

        Messages pending (unacked) for longer than *min_idle_ms* are
        claimed by *consumer* and returned for reprocessing.
        """
        if self._client is None:
            return []
        try:
            result = self._client.xautoclaim(
                self.stream, self.group, consumer,
                min_idle_time=min_idle_ms, count=count,
            )
            # xautoclaim returns (next_start_id, [(entry_id, fields), ...], deleted_ids)
            messages: list[dict[str, Any]] = []
            if isinstance(result, tuple) and len(result) >= 2:
                for entry_id, fields in result[1]:
                    msg = {"entry_id": entry_id}
                    msg.update(fields)
                    messages.append(msg)
            return messages
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)[:500]
            logger.error("Redis claim_stale failed: %s", self.last_error)
            return []

    def dlq_messages(self, count: int = 100) -> list[dict[str, Any]]:
        """Read messages from the Dead Letter Queue."""
        if self._client is None:
            return []
        try:
            results = self._client.xrange(self.dlq_stream, count=count)
            return [{"entry_id": eid, **fields} for eid, fields in results]
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)[:500]
            return []

    def health(self) -> dict[str, Any]:
        base = {
            "backend": "redis_stream",
            "ready": self._client is not None and self.last_error is None,
            "stream": self.stream,
            "group": self.group,
            "dlq_stream": self.dlq_stream,
            "last_error": self.last_error,
        }
        if self._client is not None:
            try:
                info = self._client.xpending(self.stream, self.group)
                base["pending"] = {
                    "total": info.get("pending", 0) if isinstance(info, dict) else 0,
                    "consumers": info.get("consumers", []) if isinstance(info, dict) else [],
                }
            except Exception:  # noqa: BLE001
                base["pending"] = None
        return base


event_bus = RedisEventBus(settings.redis_url, settings.event_stream) if settings.event_backend == "redis" else EventBus()
