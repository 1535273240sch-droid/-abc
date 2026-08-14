import uuid
from datetime import datetime
from typing import Any

from app.core.errors import QuantError
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc
from app.models.domain import Approval, utcnow
from app.models.enums import ApprovalResourceType, ApprovalStatus


class ApprovalService:
    def __init__(self, store: Any):
        self._store = store

    def create(
        self,
        resource_type: str,
        resource_id: str,
        requested_by: str,
        title: str,
        details: str = "",
        idempotency_key: str | None = None,
    ) -> Approval:
        try:
            rt = ApprovalResourceType(resource_type)
        except ValueError:
            raise QuantError("VALIDATION_ERROR", f"Invalid resource_type: {resource_type!r}", status_code=400)

        if idempotency_key:
            for existing in self._store.approvals.values():
                if existing.resource_id == idempotency_key:
                    return existing

        approval_id = f"appr-{uuid.uuid4().hex[:12]}"
        approval = Approval(
            approval_id=approval_id,
            resource_type=rt,
            resource_id=resource_id,
            requested_by=requested_by,
            title=title,
            details=details,
        )
        with self._store.get_lock():
            self._store.approvals[approval_id] = approval
        return approval

    def decide(self, approval_id: str, decision: str, decided_by: str, reject_reason: str | None = None) -> Approval:
        approval = self._store.approvals.get(approval_id)
        if not approval:
            raise QuantError("NOT_FOUND", f"Approval {approval_id} not found", status_code=404)

        if approval.status == ApprovalStatus.EXPIRED or approval.is_expired():
            approval.status = ApprovalStatus.EXPIRED
            raise QuantError("APPROVAL_EXPIRED", f"Approval {approval_id} has expired", status_code=400)

        if approval.status != ApprovalStatus.PENDING:
            raise QuantError(
                "APPROVAL_ALREADY_DECIDED",
                f"Approval {approval_id} is already {approval.status.value}",
                status_code=400,
            )

        try:
            new_status = ApprovalStatus(decision)
        except ValueError:
            raise QuantError("VALIDATION_ERROR", f"Invalid decision: {decision!r}", status_code=400)

        if new_status not in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
            raise QuantError("VALIDATION_ERROR", f"Decision must be 'approved' or 'rejected', got {decision!r}", status_code=400)

        approval.status = new_status
        approval.decided_by = decided_by
        approval.reject_reason = reject_reason
        approval.decided_at = utcnow()

        event_bus.publish(DomainEvent(
            event_type=event_type("governance", "approval_decided"),
            event_id=new_event_id("appr"),
            event_time=now_utc(),
            version=1,
            actor=decided_by,
            resource_type="approval",
            resource_id=approval_id,
            payload={
                "resource_type": approval.resource_type.value,
                "resource_id": approval.resource_id,
                "status": approval.status.value,
                "reject_reason": approval.reject_reason,
            },
        ))

        return approval

    def expire_due(self, now: datetime | None = None) -> list[str]:
        """Expire all pending approvals whose expires_at has passed.

        Accepts an optional ``now`` for deterministic testing.
        Returns list of approval_ids that were transitioned to expired.
        Idempotent: already-expired approvals are not re-processed.
        """
        check = now or utcnow()
        expired_ids = []
        with self._store.get_lock():
            for approval in self._store.approvals.values():
                if approval.status != ApprovalStatus.PENDING:
                    continue
                if check <= approval.expires_at:
                    continue
                approval.status = ApprovalStatus.EXPIRED
                approval.decided_at = check
                expired_ids.append(approval.approval_id)

        for aid in expired_ids:
            appr = self._store.approvals.get(aid)
            if appr:
                self._publish_expiry(appr)

        return expired_ids

    def _refresh_expiry(self, approval: Approval) -> None:
        if approval.status == ApprovalStatus.PENDING and approval.is_expired():
            approval.status = ApprovalStatus.EXPIRED
            approval.decided_at = utcnow()
            self._publish_expiry(approval)

    def _publish_expiry(self, approval: Approval) -> None:
        """Publish the domain event and project its stable audit read model."""
        payload = {
            "approval_id": approval.approval_id,
            "resource_type": approval.resource_type.value,
            "resource_id": approval.resource_id,
            "status": ApprovalStatus.EXPIRED.value,
            "expired_at": approval.expires_at.isoformat(),
        }
        domain_event = DomainEvent(
            event_type=event_type("governance", "approval_expired"),
            event_id=new_event_id("appr"),
            event_time=now_utc(),
            version=1,
            actor="system",
            resource_type="approval",
            resource_id=approval.approval_id,
            payload=payload,
        )
        event_bus.publish(domain_event)
        self._store.audit_service.record_once(
            event_type=domain_event.event_type,
            actor=domain_event.actor,
            resource_type=domain_event.resource_type,
            resource_id=domain_event.resource_id,
            details={
                "version": domain_event.version,
                "event_id": domain_event.event_id,
                "event_type": domain_event.event_type,
                "payload": payload,
            },
        )

    def get_approval(self, approval_id: str) -> Approval | None:
        approval = self._store.approvals.get(approval_id)
        if approval:
            self._refresh_expiry(approval)
        return approval

    def list_approvals(self, status: str | None = None) -> list[Approval]:
        approvals = list(self._store.approvals.values())
        for a in approvals:
            self._refresh_expiry(a)
        if status:
            approvals = [a for a in approvals if a.status.value == status]
        return sorted(approvals, key=lambda a: a.created_at, reverse=True)
