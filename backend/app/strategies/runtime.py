"""Bridge between the new strategy framework and the existing runtime.

Plugs Strategy instances into the current store / risk / order pipeline:

    Strategy.on_bar() → Signal[] → PositionSizer → risk preflight
                                  → order intents → event bus

The existing StrategyRuntimeService (legacy engines) is untouched; this
adapter runs alongside it and can replace it incrementally, kind by kind.
"""

import uuid
from decimal import Decimal
from typing import Any

from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc
from app.indicators import default_indicator_registry
from app.strategies.base import Strategy
from app.strategies.context import StrategyContext
from app.strategies.signal import Bar, Signal, SignalType
from app.strategies.sizer import DefaultSizer, PositionSizer


class FrameworkRunner:
    """Executes one strategy instance against the live store for one tick.

    Responsibilities:
    1. Build a StrategyContext wired to the store's data and services
    2. Invoke the strategy's on_bar (or on_init on first run)
    3. Translate Signals → sized quantities → risk preflight → order intents
    4. Publish domain events for every decision
    """

    def __init__(self, store: Any, sizer: PositionSizer | None = None):
        self._store = store
        self._sizer = sizer or DefaultSizer()
        self._indicators = default_indicator_registry()
        # strategy states live in the store's persisted field so they
        # survive restarts; fall back to a local dict for plain stores.
        if not hasattr(store, "strategy_states"):
            store.strategy_states = {}
        self._states: dict[str, dict] = store.strategy_states
        self._initialised: set[str] = set()

    # ── public API ────────────────────────────────────────────────────

    def run_once(
        self,
        strategy: Strategy,
        strategy_id: str,
        account_id: str = "paper-main",
        mode: str = "paper",
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Run one evaluation tick for a strategy. Returns a run report."""
        ctx = self._build_context(strategy_id)

        if strategy_id not in self._initialised:
            strategy.on_init(ctx)
            self._initialised.add(strategy_id)

        signals: list[Signal] = []
        for symbol in strategy.meta.symbols:
            bar = self._latest_bar(symbol, strategy)
            if bar is None:
                continue
            ctx.clear_cache()
            signals.extend(strategy.on_bar(ctx, bar) or [])

        results = [
            self._process_signal(sig, strategy, strategy_id, account_id, mode, dry_run)
            for sig in signals
        ]

        run_report = {
            "run_id": f"fw-run-{uuid.uuid4().hex[:12]}",
            "strategy_id": strategy_id,
            "kind": strategy.meta.kind,
            "dry_run": dry_run,
            "signal_count": len(signals),
            "results": results,
            "ran_at": now_utc().isoformat(),
        }

        event_bus.publish(DomainEvent(
            event_type=event_type("strategy", "framework_run"),
            event_id=new_event_id("framework-run"),
            event_time=now_utc(),
            version=1,
            actor=account_id,
            resource_type="strategy",
            resource_id=strategy_id,
            payload={
                "kind": strategy.meta.kind,
                "signal_count": len(signals),
                "dry_run": dry_run,
            },
        ))
        return run_report

    def state_for(self, strategy_id: str) -> dict:
        """Expose a strategy's persistent state (for inspection/debugging)."""
        return self._states.setdefault(strategy_id, {})

    # ── internals ─────────────────────────────────────────────────────

    def _build_context(self, strategy_id: str) -> StrategyContext:
        store = self._store

        def kline_provider(symbol: str, period: str, count: int) -> list[Bar]:
            svc = getattr(store, "kline_service", None)
            if svc is not None:
                return svc.get_klines(symbol, period, count)
            # Fallback: synthesise a single bar from the live ticker so
            # ticker-only strategies still work before KlineService lands.
            ticker = store.tickers.get(symbol)
            if ticker is None:
                return []
            price = Decimal(str(getattr(ticker, "last_price", "0")))
            return [Bar(symbol=symbol, open_time=0, open=price, high=price,
                        low=price, close=price, volume=Decimal("0"))]

        def ticker_provider(symbol: str) -> Any:
            return store.tickers.get(symbol)

        def indicator_provider(name: str, bars: list[Bar], params: dict) -> list[float | None]:
            return self._indicators.compute(name, bars, params)

        def position_provider(symbol: str) -> Any:
            for pos in getattr(store, "positions", {}).values():
                if getattr(pos, "symbol", None) == symbol:
                    return pos
            return None

        def cash_provider() -> Decimal:
            # Paper account cash tracking may not exist yet; default to a
            # configurable paper balance so cash_pct sizing works out of the box.
            return Decimal(str(getattr(store, "paper_cash", "100000")))

        def portfolio_provider() -> Decimal:
            cash = cash_provider()
            total = cash
            for pos in getattr(store, "positions", {}).values():
                qty = Decimal(str(getattr(pos, "quantity", "0")))
                ticker = store.tickers.get(getattr(pos, "symbol", ""))
                if ticker:
                    total += qty * Decimal(str(getattr(ticker, "last_price", "0")))
            return total

        return StrategyContext(
            strategy_id=strategy_id,
            kline_provider=kline_provider,
            ticker_provider=ticker_provider,
            indicator_provider=indicator_provider,
            position_provider=position_provider,
            cash_provider=cash_provider,
            portfolio_provider=portfolio_provider,
            state_store=self._states.setdefault(strategy_id, {}),
        )

    def _latest_bar(self, symbol: str, strategy: Strategy) -> Bar | None:
        period_map = {
            "1m": "kline_1m", "5m": "kline_5m", "15m": "kline_15m",
            "1h": "kline_1h", "4h": "kline_4h", "1d": "kline_1d",
        }
        req_period = next(
            (r.value.replace("kline_", "") for r in strategy.meta.data_requirements
             if r.value.startswith("kline_")),
            None,
        )
        svc = getattr(self._store, "kline_service", None)
        if svc is not None and req_period:
            bars = svc.get_klines(symbol, req_period, 2)
            if bars:
                return bars[-1]
        # Fallback to ticker-derived bar
        ticker = self._store.tickers.get(symbol)
        if ticker is None:
            return None
        price = Decimal(str(getattr(ticker, "last_price", "0")))
        return Bar(symbol=symbol, open_time=0, open=price, high=price,
                   low=price, close=price, volume=Decimal("0"))

    def _process_signal(
        self,
        signal: Signal,
        strategy: Strategy,
        strategy_id: str,
        account_id: str,
        mode: str,
        dry_run: bool,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "symbol": signal.symbol,
            "type": signal.type.value,
            "reason": signal.reason,
            "tag": signal.tag,
            "status": "pending",
        }

        if signal.type == SignalType.CANCEL_ALL:
            result["status"] = "skipped"
            result["note"] = "cancel_all not yet wired to order service"
            return result

        side = "buy" if signal.type in (SignalType.OPEN_LONG, SignalType.ADD_LONG) else "sell"

        # Resolve reference price for sizing
        ticker = self._store.tickers.get(signal.symbol)
        ref_price = (
            signal.limit_price
            or (Decimal(str(getattr(ticker, "last_price", "0"))) if ticker else Decimal("0"))
        )
        if ref_price <= 0:
            result["status"] = "blocked"
            result["note"] = "no reference price available"
            return result

        ctx = self._build_context(strategy_id)
        quantity = self._sizer.size(signal, ctx, ref_price)
        result["quantity"] = str(quantity)
        if quantity <= 0:
            result["status"] = "skipped"
            result["note"] = "sizer returned zero quantity"
            return result

        # ── risk preflight (existing pipeline, untouched) ──
        decision = self._store.risk_service.preflight(
            account_id=account_id,
            symbol=signal.symbol,
            side=side,
            quantity=str(quantity),
            price=str(ref_price),
            strategy_id=strategy_id,
            strategy_version=strategy.meta.version,
            mode=mode,
        )
        result["risk_decision_id"] = decision.decision_id
        result["risk_decision"] = decision.decision.value
        if decision.decision.value != "approved":
            result["status"] = "risk_rejected"
            result["note"] = decision.reject_reason
            return result

        result["status"] = "preflight_approved"
        if not dry_run:
            order = self._store.order_service.create_intent(
                client_order_id=f"fw-{uuid.uuid4().hex[:10]}-{signal.symbol}-{side}",
                account_id=account_id,
                strategy_id=strategy_id,
                strategy_version=strategy.meta.version,
                symbol=signal.symbol,
                market_type="spot",
                side=side,
                order_type="limit" if signal.limit_price else "market",
                quantity=str(quantity),
                limit_price=str(ref_price),
                mode=mode,
                risk_decision_id=decision.decision_id,
            )
            result["order_client_id"] = order.client_order_id
            result["order_status"] = order.status.value
            result["status"] = "order_created"

        return result
