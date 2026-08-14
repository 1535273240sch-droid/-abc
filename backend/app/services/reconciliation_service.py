import uuid
from decimal import Decimal
from typing import Any

from app.core.errors import QuantError
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc
from app.models.domain import ReconciliationLog, ResolutionRecord, utcnow
from app.models.enums import ReconciliationStatus, ResolutionDecision, TradeMode


class ReconciliationService:
    def __init__(self, store: Any):
        self._store = store

    def run(self, account_id: str, trace_id: str | None = None) -> ReconciliationLog:
        positions = self._store.position_service.get_positions(account_id=account_id)
        orders = self._store.order_service.get_orders(account_id=account_id)

        total_pos_qty = Decimal("0")
        total_order_filled = Decimal("0")
        total_realized_pnl = Decimal("0")
        issues = []

        for pos in positions:
            total_pos_qty += Decimal(pos.quantity)
            total_realized_pnl += Decimal(pos.realized_pnl)

        for order in orders:
            total_order_filled += Decimal(order.filled_quantity or "0")

        if total_pos_qty != total_order_filled:
            issues.append(
                f"Position quantity mismatch: total_pos={total_pos_qty} vs total_order_filled={total_order_filled}"
            )

        summary = {
            "total_positions": len(positions),
            "total_orders": len(orders),
            "total_position_qty": str(total_pos_qty.quantize(Decimal("0.00000001"))),
            "total_order_filled_qty": str(total_order_filled.quantize(Decimal("0.00000001"))),
            "total_realized_pnl": str(total_realized_pnl.quantize(Decimal("0.01"))),
            "mode": TradeMode.PAPER.value,
        }

        if issues:
            status = ReconciliationStatus.DISCREPANCY
            details = "; ".join(issues)
        else:
            status = ReconciliationStatus.CONSISTENT
            details = "All positions and orders are consistent"

        rec_id = f"rec-{uuid.uuid4().hex[:12]}"
        log = ReconciliationLog(
            reconciliation_id=rec_id,
            account_id=account_id,
            status=status,
            details=details,
            summary=summary,
        )

        with self._store.get_lock():
            self._store.reconciliation_logs.append(log)

        event_bus.publish(DomainEvent(
            event_type=event_type("reconciliation", "completed"),
            event_id=new_event_id("rec"),
            event_time=now_utc(),
            version=1,
            actor=account_id,
            resource_type="reconciliation",
            resource_id=rec_id,
            payload={"status": status.value, "details": details, "summary": summary},
        ))

        return log

    def resolve(
        self,
        reconciliation_id: str,
        decision: str,
        reason: str,
        actor: str,
        mode: str = "paper",
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> ResolutionRecord:
        _assert_paper_only(mode)

        log = next((l for l in self._store.reconciliation_logs if l.reconciliation_id == reconciliation_id), None)
        if not log:
            raise QuantError("NOT_FOUND", f"Reconciliation log {reconciliation_id} not found", status_code=404)

        if idempotency_key:
            for existing in self._store.resolution_records:
                if existing.idempotency_key == idempotency_key:
                    return existing

        try:
            dec = ResolutionDecision(decision)
        except ValueError:
            raise QuantError("VALIDATION_ERROR", f"Invalid resolution decision: {decision!r}", status_code=400)

        rec_id = f"res-{uuid.uuid4().hex[:12]}"
        record = ResolutionRecord(
            resolution_id=rec_id,
            reconciliation_id=reconciliation_id,
            account_id=log.account_id,
            decision=dec,
            reason=reason,
            actor=actor,
            idempotency_key=idempotency_key,
        )

        with self._store.get_lock():
            self._store.resolution_records.append(record)

        event_bus.publish(DomainEvent(
            event_type=event_type("reconciliation", "resolved"),
            event_id=new_event_id("res"),
            event_time=now_utc(),
            version=1,
            actor=actor,
            resource_type="reconciliation_resolution",
            resource_id=rec_id,
            payload={
                "reconciliation_id": reconciliation_id,
                "decision": dec.value,
                "reason": reason,
                "mode": mode,
            },
        ))

        return record

    def get_logs(self, account_id: str | None = None, limit: int = 50) -> list[ReconciliationLog]:
        logs = list(reversed(self._store.reconciliation_logs))
        if account_id:
            logs = [l for l in logs if l.account_id == account_id]
        return logs[:limit]

    def get_resolutions(self, reconciliation_id: str | None = None) -> list[ResolutionRecord]:
        records = list(reversed(self._store.resolution_records))
        if reconciliation_id:
            records = [r for r in records if r.reconciliation_id == reconciliation_id]
        return records


def _assert_paper_only(mode: str) -> None:
    try:
        m = TradeMode(mode)
    except ValueError:
        raise QuantError("VALIDATION_ERROR", f"Invalid mode: {mode!r}", status_code=400)
    if m != TradeMode.PAPER:
        raise QuantError("LIVE_TRADING_NOT_ALLOWED", "Only paper resolution is permitted", status_code=403)