"""Live-mode risk enhancements beyond the paper preflight rules.

Extra defences that only apply when real money can move:

- **max_position_value**: cap a single symbol's post-trade notional
  exposure at a fraction of current equity (concentration limit).
- **max_drawdown circuit breaker**: track the account equity high-water
  mark from mark-to-market logs; once drawdown from HWM exceeds the
  threshold, ALL live orders are frozen until the breaker is reset
  (explicitly, by a human, like the kill switch).

Both read their limits from settings so ops can tune without code.
"""

from decimal import Decimal
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc

logger = get_logger(__name__)


class LiveRiskService:
    def __init__(self, store: Any):
        self._store = store
        # drawdown breaker state
        self.breaker_tripped: bool = False
        self.breaker_reason: str | None = None
        self.breaker_tripped_at: str | None = None
        self.high_water_mark: Decimal | None = None

    # ── per-order checks ─────────────────────────────────────────────

    def check_order(self, account_id: str, symbol: str, side: str, quantity: str, price: str) -> list[dict]:
        """Run live-only rules; returns rules_checked entries (risk-preflight shape)."""
        results: list[dict] = []

        results.append(self._check_breaker())
        if results[-1]["passed"] is False:
            return results  # breaker frozen: remaining checks pointless

        results.append(self._check_max_position(account_id, symbol, side, quantity, price))
        return results

    def _check_breaker(self) -> dict:
        passed = not self.breaker_tripped
        entry = {
            "rule": "live_drawdown_breaker",
            "scope": "account",
            "passed": passed,
            "detail": self.breaker_reason or "drawdown within limits",
        }
        if self.high_water_mark is not None:
            entry["high_water_mark"] = str(self.high_water_mark)
        return entry

    def _check_max_position(self, account_id: str, symbol: str, side: str, quantity: str, price: str) -> dict:
        try:
            qty = Decimal(quantity)
            px = Decimal(price)
            order_notional = qty * px
        except Exception:  # noqa: BLE001
            return {"rule": "live_max_position_value", "passed": False, "detail": "invalid quantity/price"}

        current_value = self._symbol_exposure(account_id, symbol)
        projected = current_value + order_notional if side == "buy" else max(Decimal("0"), current_value - order_notional)
        equity = self._equity(account_id)
        cap = equity * Decimal(str(settings.live_max_position_pct))

        passed = projected <= cap
        return {
            "rule": "live_max_position_value",
            "scope": "symbol",
            "passed": passed,
            "limit": str(cap.quantize(Decimal("0.01"))),
            "current_exposure": str(current_value.quantize(Decimal("0.01"))),
            "projected_exposure": str(projected.quantize(Decimal("0.01"))),
            "equity": str(equity.quantize(Decimal("0.01"))),
            "detail": "projected symbol exposure within concentration cap" if passed
            else f"projected exposure {projected} exceeds cap {cap} ({settings.live_max_position_pct:.0%} of equity)",
        }

    # ── drawdown breaker ─────────────────────────────────────────────

    def update_equity(self, account_id: str, equity: Decimal) -> dict:
        """Feed a new equity observation; trips the breaker on breach."""
        if self.high_water_mark is None or equity > self.high_water_mark:
            self.high_water_mark = equity
            return {"high_water_mark": str(equity), "drawdown": "0", "tripped": self.breaker_tripped}

        drawdown = (self.high_water_mark - equity) / self.high_water_mark if self.high_water_mark > 0 else Decimal("0")
        if not self.breaker_tripped and drawdown >= Decimal(str(settings.live_max_drawdown_pct)):
            self.breaker_tripped = True
            self.breaker_reason = (
                f"equity {equity} is {drawdown:.2%} below high-water mark {self.high_water_mark} "
                f"(limit {settings.live_max_drawdown_pct:.0%})"
            )
            self.breaker_tripped_at = now_utc().isoformat()
            logger.warning("live_drawdown_breaker_tripped", drawdown=str(drawdown), hwm=str(self.high_water_mark))
            event_bus.publish(DomainEvent(
                event_type=event_type("live_risk", "drawdown_breaker_tripped"),
                event_id=new_event_id("lrisk"),
                event_time=now_utc(),
                version=1,
                actor="live_risk",
                resource_type="account",
                resource_id=account_id,
                payload={"drawdown": str(drawdown), "high_water_mark": str(self.high_water_mark), "equity": str(equity)},
            ))
            self._alert(account_id)
        return {
            "high_water_mark": str(self.high_water_mark),
            "drawdown": str(drawdown),
            "tripped": self.breaker_tripped,
        }

    def reset_breaker(self, operator: str) -> dict:
        was = self.breaker_tripped
        self.breaker_tripped = False
        self.breaker_reason = None
        self.breaker_tripped_at = None
        self.high_water_mark = None  # re-baseline on next equity update
        logger.warning("live_drawdown_breaker_reset", operator=operator, was_tripped=was)
        return {"reset": was, "operator": operator}

    def status(self) -> dict:
        return {
            "breaker_tripped": self.breaker_tripped,
            "breaker_reason": self.breaker_reason,
            "breaker_tripped_at": self.breaker_tripped_at,
            "high_water_mark": str(self.high_water_mark) if self.high_water_mark is not None else None,
            "limits": {
                "live_max_position_pct": settings.live_max_position_pct,
                "live_max_drawdown_pct": settings.live_max_drawdown_pct,
            },
        }

    # ── helpers ──────────────────────────────────────────────────────

    def _symbol_exposure(self, account_id: str, symbol: str) -> Decimal:
        total = Decimal("0")
        for pos in self._store.positions.values():
            if getattr(pos, "account_id", None) != account_id or getattr(pos, "symbol", None) != symbol:
                continue
            qty = Decimal(str(getattr(pos, "quantity", "0")))
            avg = Decimal(str(getattr(pos, "average_price", "0") or "0"))
            total += qty * avg
        return total

    def _equity(self, account_id: str) -> Decimal:
        # Cash + positions at average cost. Conservative (no MTM inflation).
        equity = Decimal(str(getattr(self._store, "paper_cash", "100000")))
        for pos in self._store.positions.values():
            if getattr(pos, "account_id", None) != account_id:
                continue
            qty = Decimal(str(getattr(pos, "quantity", "0")))
            avg = Decimal(str(getattr(pos, "average_price", "0") or "0"))
            equity += qty * avg
        return equity

    def _alert(self, account_id: str) -> None:
        svc = getattr(self._store, "alert_notification_service", None)
        if svc is not None:
            try:
                svc.alert(
                    title="实盘最大回撤熔断触发",
                    message=f"账户 {account_id} 权益回撤超过 {settings.live_max_drawdown_pct:.0%} 熔断阈值,所有实盘订单已冻结,需人工重置。",
                    severity="critical",
                    source="live_risk",
                    details=self.status(),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("live_risk_alert_error", error=str(exc)[:200])
