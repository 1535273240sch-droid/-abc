import uuid
from typing import Any

from app.core.errors import QuantError
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc
from app.models.domain import StrategyRun
from app.models.enums import TradeMode
from app.services.strategy_engines import StrategyEngineRegistry, default_registry


class StrategyRuntimeService:
    """Small, deterministic Paper runtime that preserves the blueprint gates.

    It deliberately produces intents only after a risk preflight. A real
    scheduler and exchange adapter can replace this service without changing
    the API contract.

    Strategy signal generation is delegated to pluggable
    :class:`StrategyEngine` instances registered in *engine_registry*.
    New strategy kinds can be added by registering an engine without
    changing this service.
    """

    def __init__(self, store: Any, engine_registry: StrategyEngineRegistry | None = None):
        self._store = store
        self._engine_registry = engine_registry or default_registry()
        self.scheduler_last_run_at: str | None = None
        self.scheduler_error: str | None = None
        self.scheduler_runs = 0

    def run_scheduled(self) -> int:
        count = 0
        for strategy in self._store.strategy_service.get_strategies():
            if strategy.status == "active":
                self.run(strategy.strategy_id, account_id="paper-main", mode="paper", dry_run=True)
                count += 1
        self.scheduler_last_run_at = now_utc().isoformat()
        self.scheduler_runs += 1
        self.scheduler_error = None
        return count

    def run(self, strategy_id: str, account_id: str = "paper-main", mode: str = "paper", dry_run: bool = True) -> StrategyRun:
        if mode != TradeMode.PAPER.value:
            self._store.live_mode_service.assert_live_allowed(account_id=account_id)
        strategy = self._store.strategy_service.get(strategy_id)
        if not strategy:
            raise QuantError("NOT_FOUND", f"Strategy {strategy_id} not found", status_code=404)
        if strategy.status != "active":
            raise QuantError("STRATEGY_NOT_ACTIVE", f"Strategy {strategy_id} is not active", status_code=409)

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        quality = self._store.market_service.quality()
        signals = self._signals_for(strategy, quality)
        orders: list[dict] = []
        for signal in signals:
            if signal.get("action") != "buy":
                continue
            ticker = self._store.tickers.get(signal["symbol"])
            if not ticker:
                signal["status"] = "blocked"
                signal["reason"] = "ticker_missing"
                continue
            decision = self._store.risk_service.preflight(
                account_id=account_id,
                symbol=signal["symbol"],
                side="buy",
                quantity=signal["quantity"],
                price=ticker.last_price,
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.version,
                mode=mode,
            )
            signal["risk_decision_id"] = decision.decision_id
            signal["risk_decision"] = decision.decision.value
            if decision.decision.value != "approved":
                signal["status"] = "risk_rejected"
                signal["reason"] = decision.reject_reason
                continue
            signal["status"] = "preflight_approved"
            if not dry_run:
                order = self._store.order_service.create_intent(
                    client_order_id=f"{run_id}-{signal['symbol']}-buy",
                    account_id=account_id,
                    strategy_id=strategy.strategy_id,
                    strategy_version=strategy.version,
                    symbol=signal["symbol"],
                    market_type="spot",
                    side="buy",
                    order_type="limit",
                    quantity=signal["quantity"],
                    limit_price=ticker.last_price,
                    mode=mode,
                    risk_decision_id=decision.decision_id,
                )
                orders.append({"client_order_id": order.client_order_id, "status": order.status.value})

        status = "completed" if not any(s.get("status") == "risk_rejected" for s in signals) else "completed_with_rejections"
        run = StrategyRun(
            run_id=run_id,
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.version,
            account_id=account_id,
            mode=TradeMode.PAPER,
            dry_run=dry_run,
            status=status,
            data_quality=quality,
            signals=signals,
            orders=orders,
            reason="Paper dry-run" if dry_run else "Paper order intents created",
        )
        with self._store.get_lock():
            self._store.strategy_runs[run_id] = run
        event_bus.publish(DomainEvent(
            event_type=event_type("strategy", "run_completed"),
            event_id=new_event_id("strategy-run"),
            event_time=now_utc(),
            version=1,
            actor=account_id,
            resource_type="strategy_run",
            resource_id=run_id,
            payload={"strategy_id": strategy.strategy_id, "status": status, "dry_run": dry_run, "signal_count": len(signals)},
        ))
        return run

    def list_runs(self, strategy_id: str | None = None) -> list[StrategyRun]:
        runs = list(self._store.strategy_runs.values())
        if strategy_id:
            runs = [run for run in runs if run.strategy_id == strategy_id]
        return sorted(runs, key=lambda run: run.created_at, reverse=True)

    def _signals_for(self, strategy: Any, quality: dict) -> list[dict]:
        """Delegate signal generation to the pluggable engine registry."""
        engine = self._engine_registry.get(strategy.kind)
        return engine.generate_signals(strategy, quality, self._store.tickers)
