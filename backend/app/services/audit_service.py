import uuid
from typing import Any

from app.models.domain import AuditEvent


class AuditService:
    def __init__(self, store: Any):
        self._store = store

    def record(
        self,
        event_type: str,
        actor: str,
        resource_type: str,
        resource_id: str,
        details: dict | None = None,
        ip_address: str | None = None,
        trace_id: str | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            actor=actor,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            trace_id=trace_id,
        )
        with self._store.get_lock():
            self._store.audit_events.append(event)
        return event

    def record_once(
        self,
        event_type: str,
        actor: str,
        resource_type: str,
        resource_id: str,
        details: dict | None = None,
        ip_address: str | None = None,
        trace_id: str | None = None,
    ) -> AuditEvent:
        """Record a read-model event exactly once for a resource.

        Approval expiry can be observed by both the explicit sweep and the
        lazy API refresh path.  The in-memory store is process-local, so the
        uniqueness check and append deliberately share the store lock.
        """
        with self._store.get_lock():
            for existing in self._store.audit_events:
                if existing.event_type == event_type and existing.resource_id == resource_id:
                    return existing
            event = AuditEvent(
                event_id=str(uuid.uuid4()),
                event_type=event_type,
                actor=actor,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                ip_address=ip_address,
                trace_id=trace_id,
            )
            self._store.audit_events.append(event)
            return event

    def get_events(self, limit: int = 100, offset: int = 0) -> list[AuditEvent]:
        events = list(reversed(self._store.audit_events))
        return events[offset:offset + limit]
