"""Live-trading guard rails: balance checks, position reconciliation,
and automatic freeze on drift.

These are the *last line of defence* before real money moves:

1. BalanceGuard  — query the exchange's real available balance before
   every order; reject when insufficient (paper mode uses paper_cash).
2. PositionRecon — compare local ledger vs exchange actual holdings;
   on drift beyond tolerance, raise a critical alert and freeze new
   entries until manually resolved.

Both are adapter-agnostic: they work against any object exposing
``get_balance(asset)`` / ``get_positions()`` — the paper adapter today,
real exchange adapters tomorrow.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.core.logging import get_logger
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc

logger = get_logger(__name__)

_DRIFT_TOLERANCE = Decimal("0.0001")   # 0.01% relative tolerance


class LiveGuardService:
    """Pre-trade balance checks + post-trade position reconciliation."""

    def __init__(self, store: Any):
        self._store = store
        self.frozen: bool = False
        self.freeze_reason: str | None = None
        self.frozen_at: str | None = None
        self.last_recon_at: str | None = None
        self.last_recon_result: dict[str, Any] | None = None

    # ── 1. balance guard ──────────────────────────────────────────────

    def check_balance(
        self,
        account_id: str,
        quote_asset: str,
        required_quote: Decimal,
        adapter: Any = None,
    ) -> dict[str, Any]:
        """Verify sufficient quote-asset balance before an order.

        Returns a decision dict; ``allowed=False`` means the order must
        be rejected before it reaches the exchange.
        """
        available = self._available_balance(quote_asset, adapter)
        allowed = available >= required_quote
        decision = {
            "check": "balance",
            "account_id": account_id,
            "quote_asset": quote_asset,
            "required": str(required_quote),
            "available": str(available),
            "allowed": allowed,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        if not allowed:
            logger.warning(
                "balance_check_rejected",
                asset=quote_asset,
                required=str(required_quote),
                available=str(available),
            )
            self._raise(
                title="余额不足拒单",
                message=f"账户 {account_id} 的 {quote_asset} 可用余额 {available} 低于订单所需 {required_quote}，订单已在进入交易所前拦截。",
                severity="warning",
                details=decision,
            )
        return decision

    def _available_balance(self, asset: str, adapter: Any = None) -> Decimal:
        # real adapter path (future live mode)
        if adapter is not None and hasattr(adapter, "get_balance"):
            try:
                bal = adapter.get_balance(asset)
                return Decimal(str(bal))
            except Exception as exc:  # noqa: BLE001
                logger.warning("adapter_balance_error", error=str(exc)[:200])
                return Decimal("0")
        # paper fallback
        return Decimal(str(getattr(self._store, "paper_cash", "100000")))

    # ── 2. freeze control ─────────────────────────────────────────────

    def is_frozen(self) -> bool:
        return self.frozen

    def freeze(self, reason: str) -> None:
        if not self.frozen:
            self.frozen = True
            self.freeze_reason = reason
            self.frozen_at = datetime.now(timezone.utc).isoformat()
            logger.warning("live_guard_frozen", reason=reason)

    def unfreeze(self, operator: str = "manual") -> dict[str, Any]:
        was = self.frozen
        self.frozen = False
        self.freeze_reason = None
        self.frozen_at = None
        logger.info("live_guard_unfrozen", operator=operator, was_frozen=was)
        return {"unfrozen": was, "operator": operator}

    # ── 3. position reconciliation ────────────────────────────────────

    def reconcile_positions(self, adapter: Any = None) -> dict[str, Any]:
        """Compare local ledger positions vs exchange actual holdings.

        On drift beyond tolerance: freeze new entries + critical alert.
        Returns a reconciliation report.
        """
        local = self._local_positions()
        remote = self._remote_positions(adapter)

        diffs: list[dict[str, Any]] = []
        symbols = set(local) | set(remote)
        for symbol in sorted(symbols):
            l_qty = local.get(symbol, Decimal("0"))
            r_qty = remote.get(symbol, Decimal("0"))
            if l_qty == r_qty:
                continue
            base = max(abs(l_qty), abs(r_qty), Decimal("0.00000001"))
            rel = abs(l_qty - r_qty) / base
            diffs.append({
                "symbol": symbol,
                "local": str(l_qty),
                "remote": str(r_qty),
                "abs_diff": str(abs(l_qty - r_qty)),
                "rel_diff": f"{rel:.6%}",
                "beyond_tolerance": rel > _DRIFT_TOLERANCE,
            })

        drifted = any(d["beyond_tolerance"] for d in diffs)
        report = {
            "reconciled_at": datetime.now(timezone.utc).isoformat(),
            "symbols_checked": len(symbols),
            "diffs": diffs,
            "drifted": drifted,
            "frozen": self.frozen,
        }
        self.last_recon_at = report["reconciled_at"]
        self.last_recon_result = report

        if drifted:
            self.freeze("position_reconciliation_drift")
            self._raise(
                title="持仓对账差异，已冻结新开仓",
                message=f"检测到 {len([d for d in diffs if d['beyond_tolerance']])} 个交易对的本地账本与交易所实际持仓差异超过容差。系统已自动冻结新开仓，请人工核对后解冻。",
                severity="critical",
                details={"diffs": diffs},
            )
            event_bus.publish(DomainEvent(
                event_type=event_type("live_guard", "recon_drift"),
                event_id=new_event_id("recon"),
                event_time=now_utc(),
                version=1,
                actor="live_guard",
                resource_type="account",
                resource_id="paper-main",
                payload={"diff_count": len(diffs), "frozen": True},
            ))
        logger.info("position_recon_done", symbols=len(symbols), drifted=drifted)
        return report

    def _local_positions(self) -> dict[str, Decimal]:
        out: dict[str, Decimal] = {}
        for pos in getattr(self._store, "positions", {}).values():
            symbol = getattr(pos, "symbol", None)
            if symbol:
                out[symbol] = out.get(symbol, Decimal("0")) + Decimal(str(getattr(pos, "quantity", "0")))
        return out

    def _remote_positions(self, adapter: Any = None) -> dict[str, Decimal]:
        if adapter is not None and hasattr(adapter, "get_positions"):
            try:
                raw = adapter.get_positions()  # expected: {symbol: qty}
                return {s: Decimal(str(q)) for s, q in raw.items()}
            except Exception as exc:  # noqa: BLE001
                logger.warning("adapter_positions_error", error=str(exc)[:200])
                return {}
        # paper mode: remote == local (no drift by construction)
        return self._local_positions()

    # ── alert helper ──────────────────────────────────────────────────

    def _raise(self, title: str, message: str, severity: str, details: dict[str, Any]) -> None:
        svc = getattr(self._store, "alert_notification_service", None)
        if svc is not None:
            try:
                svc.alert(title=title, message=message, severity=severity, source="live_guard", details=details)
            except Exception as exc:  # noqa: BLE001
                logger.warning("live_guard_alert_error", error=str(exc)[:200])

    def status(self) -> dict[str, Any]:
        return {
            "frozen": self.frozen,
            "freeze_reason": self.freeze_reason,
            "frozen_at": self.frozen_at,
            "last_recon_at": self.last_recon_at,
            "last_recon_drifted": (self.last_recon_result or {}).get("drifted"),
        }
