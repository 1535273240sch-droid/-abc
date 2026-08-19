from typing import Any

from app.core.errors import QuantError
from app.core.logging import get_logger
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc
from app.models.domain import KillSwitchState, utcnow
from app.models.enums import ApprovalResourceType, ApprovalStatus, KillSwitchStatus, TradeMode
from app.services.alert_notification_service import AlertLevel

logger = get_logger(__name__)


class KillSwitchService:
    def __init__(self, store: Any):
        self._store = store
        with self._lock_ctx():
            if store.kill_switch_state is None:
                store.kill_switch_state = KillSwitchState()

    def _lock_ctx(self):
        if hasattr(self._store, "get_lock"):
            return self._store.get_lock()
        from contextlib import nullcontext
        return nullcontext()

    @property
    def _state(self) -> KillSwitchState:
        return self._store.kill_switch_state

    def is_active(self) -> bool:
        return self._state.status == KillSwitchStatus.ACTIVE

    def assert_not_active(self, action: str = "perform this action") -> None:
        if self.is_active():
            raise QuantError("KILL_SWITCH_ACTIVE", f"Cannot {action}: kill switch is active", status_code=503)

    def trigger(self, triggered_by: str, reason: str) -> KillSwitchState:
        with self._lock_ctx():
            self._state.status = KillSwitchStatus.ACTIVE
            self._state.triggered_by = triggered_by
            self._state.trigger_reason = reason
            self._state.triggered_at = utcnow()
            self._state.recovered_by = None
            self._state.recovered_at = None

            event_bus.publish(DomainEvent(
                event_type=event_type("governance", "kill_switch_triggered"),
                event_id=new_event_id("ks"),
                event_time=now_utc(),
                version=1,
                actor=triggered_by,
                resource_type="kill_switch",
                resource_id="system",
                payload={"reason": reason, "status": KillSwitchStatus.ACTIVE.value},
            ))

        # ?????????????
        alert_service = getattr(self._store, "alert_notification_service", None)
        if alert_service is not None:
            try:
                alert_service.send_alert(
                    level=AlertLevel.CRITICAL,
                    title=f"??????????{reason}",
                    message=f"Kill-Switch has been triggered by '{triggered_by}'. Reason: {reason}. All live trading and order submissions are halted.",
                    metadata={
                        "triggered_by": triggered_by,
                        "reason": reason,
                        "status": KillSwitchStatus.ACTIVE.value,
                        "triggered_at": self._state.triggered_at.isoformat() if self._state.triggered_at else None,
                    },
                    source="kill_switch",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("kill_switch_alert_broadcast_error", error=str(exc)[:200])

        return self._state

    def recover(self, recovered_by: str, reason: str, approval_id: str, mode: str = "paper") -> KillSwitchState:
        _assert_paper_only(mode)
        with self._lock_ctx():
            if not self.is_active():
                raise QuantError("INVALID_STATE", "Kill switch is not active, cannot recover", status_code=400)

            approval = self._store.approvals.get(approval_id)
            if not approval:
                raise QuantError("NOT_FOUND", f"Approval {approval_id} not found", status_code=404)
            if approval.resource_type != ApprovalResourceType.KILL_SWITCH_RECOVERY:
                raise QuantError(
                    "INVALID_APPROVAL_TYPE",
                    f"Approval {approval_id} is not a kill_switch_recovery approval",
                    status_code=400,
                )
            if approval.status == ApprovalStatus.EXPIRED or approval.is_expired():
                approval.status = ApprovalStatus.EXPIRED
                raise QuantError("APPROVAL_EXPIRED", f"Approval {approval_id} has expired", status_code=400)
            if approval.status == ApprovalStatus.PENDING:
                raise QuantError("APPROVAL_PENDING", f"Approval {approval_id} is still pending", status_code=400)
            if approval.status == ApprovalStatus.REJECTED:
                raise QuantError(
                    "APPROVAL_REJECTED",
                    f"Approval {approval_id} was rejected: {approval.reject_reason}",
                    status_code=400,
                )
            if approval.status != ApprovalStatus.APPROVED:
                raise QuantError("APPROVAL_NOT_APPROVED", f"Approval {approval_id} is not approved", status_code=400)

            self._state.status = KillSwitchStatus.INACTIVE
            self._state.recovered_by = recovered_by
            self._state.recovered_at = utcnow()

            event_bus.publish(DomainEvent(
                event_type=event_type("governance", "kill_switch_recovered"),
                event_id=new_event_id("ks"),
                event_time=now_utc(),
                version=1,
                actor=recovered_by,
                resource_type="kill_switch",
                resource_id="system",
                payload={"reason": reason, "status": KillSwitchStatus.INACTIVE.value},
            ))

        # ??????????
        alert_service = getattr(self._store, "alert_notification_service", None)
        if alert_service is not None:
            try:
                alert_service.send_alert(
                    level=AlertLevel.INFO,
                    title=f"??????????{reason}",
                    message=f"Kill-Switch has been recovered by '{recovered_by}' with approval '{approval_id}'. Reason: {reason}.",
                    metadata={
                        "recovered_by": recovered_by,
                        "approval_id": approval_id,
                        "reason": reason,
                        "status": KillSwitchStatus.INACTIVE.value,
                        "recovered_at": self._state.recovered_at.isoformat() if self._state.recovered_at else None,
                    },
                    source="kill_switch",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("kill_switch_recover_alert_error", error=str(exc)[:200])

        return self._state

    def get_state(self) -> KillSwitchState:
        return self._state


def _assert_paper_only(mode: str) -> None:
    try:
        m = TradeMode(mode)
    except ValueError:
        raise QuantError("VALIDATION_ERROR", f"Invalid mode: {mode!r}", status_code=400)
    if m != TradeMode.PAPER:
        raise QuantError("LIVE_TRADING_NOT_ALLOWED", "Only paper mode is permitted for kill-switch recovery", status_code=403)
