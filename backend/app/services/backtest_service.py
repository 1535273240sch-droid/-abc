import hashlib
import uuid
from decimal import Decimal
from typing import Any

from app.core.errors import QuantError
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc
from app.models.domain import Backtest, utcnow
from app.models.enums import BacktestStatus, TradeMode
from app.services.backtest_engine import BacktestEngine


class BacktestService:
    def __init__(self, store: Any):
        self._store = store

    def execute(
        self,
        strategy_id: str,
        strategy_version: str,
        data_snapshot: str,
        fee_model: str,
        slippage_model: str,
        initial_capital: str,
        mode: str,
        account_id: str = "paper-main",
        idempotency_key: str | None = None,
    ) -> Backtest:
        _assert_paper_only(mode)
        _validate_capital(initial_capital)

        if idempotency_key:
            with self._store.get_lock():
                for existing in self._store.backtests.values():
                    if existing.idempotency_key == idempotency_key:
                        return existing

        strategy = self._store.strategies.get(strategy_id)
        if not strategy:
            raise QuantError("NOT_FOUND", f"Strategy {strategy_id} not found", status_code=404)
        if strategy.version != strategy_version:
            raise QuantError(
                "INVALID_STRATEGY_VERSION",
                f"Strategy {strategy_id} version {strategy_version} does not match registered version {strategy.version}",
                status_code=400,
            )

        backtest_id = f"bt-{uuid.uuid4().hex[:12]}"
        run_env = "paper-backtest-engine-v2"

        bt = Backtest(
            backtest_id=backtest_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            parameters=strategy.parameters,
            data_snapshot=data_snapshot,
            fee_model=fee_model,
            slippage_model=slippage_model,
            run_environment=run_env,
            initial_capital=initial_capital,
            account_id=account_id,
            mode=TradeMode(mode),
            idempotency_key=idempotency_key,
        )
        bt.code_ref = strategy.code_ref

        engine_result = self._run_engine(strategy, data_snapshot, fee_model, slippage_model, initial_capital)
        bt.status = BacktestStatus.COMPLETED
        bt.net_profit = engine_result.net_profit
        bt.sharpe_ratio = engine_result.sharpe_ratio
        bt.max_drawdown = engine_result.max_drawdown
        bt.win_rate = engine_result.win_rate
        bt.total_trades = engine_result.total_trades
        bt.completed_at = utcnow()

        with self._store.get_lock():
            self._store.backtests[backtest_id] = bt

        event_bus.publish(DomainEvent(
            event_type=event_type("research", "backtest_completed"),
            event_id=new_event_id("bt"),
            event_time=now_utc(),
            version=1,
            actor=account_id,
            resource_type="backtest",
            resource_id=backtest_id,
            payload={
                "strategy_id": strategy_id,
                "strategy_version": strategy_version,
                "net_profit": bt.net_profit,
                "sharpe_ratio": bt.sharpe_ratio,
                "total_trades": bt.total_trades,
                "status": bt.status.value,
            },
        ))

        return bt

    def get_backtest(self, backtest_id: str) -> Backtest | None:
        return self._store.backtests.get(backtest_id)

    def list_backtests(self, account_id: str | None = None) -> list[Backtest]:
        bts = list(self._store.backtests.values())
        if account_id:
            bts = [b for b in bts if b.account_id == account_id]
        return sorted(bts, key=lambda b: b.created_at, reverse=True)

    def _run_engine(self, strategy: Any, data_snapshot: str, fee_model: str, slippage_model: str, initial_capital: str) -> Any:
        from app.strategies.registry import registry as strategy_registry

        bars = self._bars_for_snapshot(data_snapshot, getattr(strategy, "symbols", None) or ("BTCUSDT",))
        if not bars:
            return _simulate_fallback(initial_capital)

        strategy_cls = strategy_registry.get(strategy.kind)
        if strategy_cls is None:
            return _simulate_fallback(initial_capital)

        return BacktestEngine(
            bars=bars,
            strategy_cls=strategy_cls,
            params=strategy.parameters or {},
            initial_capital=initial_capital,
            fee_model=fee_model,
            slippage_model=slippage_model,
        ).run()

    def _bars_for_snapshot(self, data_snapshot: str, symbols: tuple[str, ...]) -> list[Any]:
        symbol = symbols[0] if symbols else "BTCUSDT"
        try:
            return self._store.historical_data_service.get_bars(symbol, "1h", limit=5000)
        except Exception as exc:  # noqa: BLE001
            return []


def _assert_paper_only(mode: str) -> None:
    try:
        m = TradeMode(mode)
    except ValueError:
        raise QuantError("VALIDATION_ERROR", f"Invalid trading mode: {mode!r}", status_code=400)
    if m != TradeMode.PAPER:
        raise QuantError(
            "LIVE_TRADING_NOT_ALLOWED",
            "Only paper trading is permitted for backtests in this environment",
            status_code=403,
        )


def _validate_capital(capital: str) -> None:
    if not isinstance(capital, str) or not capital.strip():
        raise QuantError("VALIDATION_ERROR", "initial_capital must be a non-empty string", status_code=400)
    try:
        d = Decimal(capital.strip())
    except Exception:
        raise QuantError("VALIDATION_ERROR", f"initial_capital is not a valid decimal: {capital!r}", status_code=400)
    if not d.is_finite() or d <= 0:
        raise QuantError("VALIDATION_ERROR", f"initial_capital must be positive and finite, got {capital!r}", status_code=400)


def _simulate_fallback(capital_str: str) -> Any:
    from app.services.backtest_engine import BacktestResult
    capital = Decimal(capital_str)
    return BacktestResult(
        status="completed",
        final_equity=capital,
        net_profit="0",
        sharpe_ratio="0",
        max_drawdown="0%",
        win_rate="0%",
        total_trades=0,
        completed_at=utcnow().isoformat(),
    )
