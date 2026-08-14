import uuid
from decimal import Decimal
from typing import Any

from app.core.errors import QuantError
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc
from app.models.domain import PortfolioTarget
from app.models.enums import TradeMode


class PortfolioTargetService:
    def __init__(self, store: Any):
        self._store = store

    def set_target(
        self,
        account_id: str,
        strategy_id: str,
        strategy_version: str,
        symbol: str,
        target_quantity: str,
        target_weight: str | None = None,
        mode: str = "paper",
        idempotency_key: str | None = None,
    ) -> PortfolioTarget:
        _assert_paper_only(mode)
        _validate_quantity(target_quantity)

        if idempotency_key:
            with self._store.get_lock():
                for existing in self._store.portfolio_targets.values():
                    if existing.idempotency_key == idempotency_key:
                        return existing

        current_qty = _get_current_quantity(self._store, account_id, symbol)
        target_id = f"pt-{uuid.uuid4().hex[:12]}"

        target = PortfolioTarget(
            target_id=target_id,
            account_id=account_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            symbol=symbol,
            target_quantity=target_quantity,
            current_quantity=current_qty,
            target_weight=target_weight,
            mode=TradeMode(mode),
            idempotency_key=idempotency_key,
        )

        with self._store.get_lock():
            self._store.portfolio_targets[target_id] = target

        event_bus.publish(DomainEvent(
            event_type=event_type("portfolio", "target_created"),
            event_id=new_event_id("pt"),
            event_time=now_utc(),
            version=1,
            actor=account_id,
            resource_type="portfolio_target",
            resource_id=target_id,
            payload={
                "symbol": symbol,
                "strategy_id": strategy_id,
                "target_quantity": target_quantity,
                "current_quantity": current_qty,
                "delta": target.delta,
                "mode": mode,
            },
        ))

        return target

    def get_target(self, target_id: str) -> PortfolioTarget | None:
        return self._store.portfolio_targets.get(target_id)

    def list_targets(self, account_id: str | None = None) -> list[PortfolioTarget]:
        targets = list(self._store.portfolio_targets.values())
        if account_id:
            targets = [t for t in targets if t.account_id == account_id]
        return sorted(targets, key=lambda t: t.created_at, reverse=True)


def _assert_paper_only(mode: str) -> None:
    try:
        m = TradeMode(mode)
    except ValueError:
        raise QuantError("VALIDATION_ERROR", f"Invalid mode: {mode!r}", status_code=400)
    if m != TradeMode.PAPER:
        raise QuantError("LIVE_TRADING_NOT_ALLOWED", "Only paper portfolio targets are permitted", status_code=403)


def _validate_quantity(qty: str) -> None:
    if not isinstance(qty, str) or not qty.strip():
        raise QuantError("VALIDATION_ERROR", "target_quantity must be a non-empty string", status_code=400)
    try:
        d = Decimal(qty.strip())
    except Exception:
        raise QuantError("VALIDATION_ERROR", f"target_quantity is not a valid decimal: {qty!r}", status_code=400)
    if not d.is_finite() or d < 0:
        raise QuantError("VALIDATION_ERROR", f"target_quantity must be non-negative and finite", status_code=400)


def _get_current_quantity(store: Any, account_id: str, symbol: str) -> str:
    total = Decimal("0")
    for pos in store.positions.values():
        if pos.account_id == account_id and pos.symbol == symbol:
            total += Decimal(pos.quantity)
    return str(total.quantize(Decimal("0.00000001")))