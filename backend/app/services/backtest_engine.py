"""Bar-by-bar backtest engine for the pluggable strategy framework.

Produces realistic fills (fees + slippage), an equity curve, and the
standard performance metrics a quant researcher expects:

- net profit / total return
- Sharpe ratio (annualized)
- max drawdown
- win rate / profit factor
- average win / loss / trade
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Type

from app.core.errors import QuantError
from app.core.logging import get_logger
from app.strategies.base import Strategy
from app.strategies.context import StrategyContext
from app.strategies.signal import Bar, Signal, SignalType
from app.strategies.sizer import DefaultSizer

logger = get_logger(__name__)


@dataclass
class BacktestPosition:
    symbol: str
    quantity: Decimal
    entry_price: Decimal
    entry_time: int
    entry_fee: Decimal = Decimal("0")
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None


@dataclass(frozen=True)
class BacktestTrade:
    entry_time: int
    exit_time: int
    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    gross_pnl: Decimal
    fee_paid: Decimal
    net_pnl: Decimal
    return_pct: Decimal
    exit_reason: str


@dataclass
class BacktestResult:
    status: str
    equity_curve: list[tuple[int, Decimal]] = field(default_factory=list)
    trades: list[BacktestTrade] = field(default_factory=list)
    final_equity: Decimal = Decimal("0")
    metrics: dict[str, Any] = field(default_factory=dict)
    net_profit: str = "0"
    sharpe_ratio: str = "0"
    max_drawdown: str = "0%"
    win_rate: str = "0%"
    total_trades: int = 0
    completed_at: str | None = None


class FeeModel:
    @staticmethod
    def resolve(model: str, **kwargs: Any) -> Callable[[Decimal, Decimal, bool], Decimal]:
        m = (model or "simple").lower().strip()
        if m in ("none", "zero", "0"):
            return lambda qty, price, is_maker=False: Decimal("0")
        if m == "simple":
            rate = Decimal(str(kwargs.get("fee_bps", 10))) / Decimal("10000")
            return lambda qty, price, is_maker=False: qty * price * rate
        if m == "tiered":
            maker = Decimal(str(kwargs.get("maker_bps", 8))) / Decimal("10000")
            taker = Decimal(str(kwargs.get("taker_bps", 10))) / Decimal("10000")
            return lambda qty, price, is_maker=False: qty * price * (maker if is_maker else taker)
        raise QuantError("VALIDATION_ERROR", f"unknown fee model: {model!r}", status_code=400)


class SlippageModel:
    @staticmethod
    def resolve(model: str, **kwargs: Any) -> Callable[[str, Decimal, Bar], Decimal]:
        m = (model or "none").lower().strip()
        if m in ("none", "zero", "0"):
            return lambda side, price, bar: price
        if m == "fixed_bps":
            bps = Decimal(str(kwargs.get("slippage_bps", 5))) / Decimal("10000")
            return lambda side, price, bar: (
                price * (Decimal("1") + bps) if side == "buy" else price * (Decimal("1") - bps)
            )
        if m == "fixed_price":
            amount = Decimal(str(kwargs.get("slippage_price", 10)))
            return lambda side, price, bar: (price + amount if side == "buy" else price - amount)
        if m == "volatility":
            atr_mult = Decimal(str(kwargs.get("atr_mult", 0.5)))
            return SlippageModel._volatility(atr_mult)
        raise QuantError("VALIDATION_ERROR", f"unknown slippage model: {model!r}", status_code=400)

    @staticmethod
    def _volatility(atr_mult: Decimal) -> Callable[[str, Decimal, Bar], Decimal]:
        def _apply(side: str, price: Decimal, bar: Bar) -> Decimal:
            range_ = (bar.high - bar.low) if bar.high > bar.low else price * Decimal("0.001")
            slip = range_ * atr_mult
            return (price + slip) if side == "buy" else (price - slip)
        return _apply


class BacktestEngine:
    """Deterministic bar-by-bar driver for :class:`Strategy` subclasses."""

    def __init__(
        self,
        bars: list[Bar],
        strategy_cls: type[Strategy],
        params: dict[str, Any],
        initial_capital: str = "100000",
        fee_model: str = "simple",
        slippage_model: str = "none",
        sizer_cls: type | None = None,
        max_bars: int = 50000,
    ):
        if not bars:
            raise QuantError("VALIDATION_ERROR", "backtest requires at least one bar", status_code=400)
        if any(b.symbol != bars[0].symbol for b in bars):
            raise QuantError("VALIDATION_ERROR", "mixed-symbol bars are not supported in a single backtest run", status_code=400)
        if len(bars) > max_bars:
            bars = list(bars[-max_bars:])
        self.bars = bars
        self.strategy = strategy_cls(params)
        self.initial_capital = Decimal(initial_capital)
        self.fee_fn = FeeModel.resolve(fee_model)
        self.slippage_fn = SlippageModel.resolve(slippage_model)
        self.sizer_cls = sizer_cls or DefaultSizer
        self.symbol = bars[0].symbol

    def run(self) -> BacktestResult:
        strategy = self.strategy
        warmup = getattr(strategy.meta, "warmup_bars", 0) or 0

        state: dict[str, Any] = {"cash": self.initial_capital}
        trades: list[BacktestTrade] = []
        equity_curve: list[tuple[int, Decimal]] = []
        hwm = self.initial_capital
        max_dd = Decimal("0")

        for idx, bar in enumerate(self.bars):
            position = state.get("_position")

            if idx >= warmup:
                ctx = self._context(idx, state, position, bar)
                try:
                    signals = strategy.on_bar(ctx, bar)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("backtest_signal_error", idx=idx, error=str(exc)[:200])
                    signals = []

                if not isinstance(signals, list):
                    signals = []

                # Intra-bar risk management before new signals
                if position is not None and position.symbol == bar.symbol:
                    closeout = self._check_stops(position, bar)
                    if closeout is not None:
                        trades.append(closeout)
                        state["cash"] = state["cash"] + closeout.net_pnl + closeout.entry_price * closeout.quantity
                        position = None
                        state["_position"] = None

                for signal in signals:
                    if not isinstance(signal, Signal):
                        continue
                    if signal.symbol != self.symbol:
                        continue
                    self._apply_signal(signal, bar, state)
                    position = state.get("_position")

            # Mark-to-market at bar close
            equity = state["cash"] + (
                position.quantity * bar.close if position is not None else Decimal("0")
            )
            hwm = max(hwm, equity)
            dd = (hwm - equity) / hwm if hwm > 0 else Decimal("0")
            max_dd = max(max_dd, dd)
            equity_curve.append((bar.open_time, equity))

        # Close any open position at last close
        position = state.get("_position")
        if position is not None:
            last = self.bars[-1]
            closeout = self._close_position(position, last.close, last.open_time, "end_of_data")
            trades.append(closeout)
            state["cash"] = state["cash"] + closeout.net_pnl + closeout.entry_price * closeout.quantity
            state["_position"] = None

        final_equity = state["cash"]
        metrics = self._metrics(trades, equity_curve, final_equity, max_dd)

        result = BacktestResult(
            status="completed",
            equity_curve=equity_curve,
            trades=trades,
            final_equity=final_equity,
            metrics=metrics,
            net_profit=metrics["net_profit"],
            sharpe_ratio=metrics["sharpe_ratio"],
            max_drawdown=metrics["max_drawdown"],
            win_rate=metrics["win_rate"],
            total_trades=len(trades),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        return result

    @staticmethod
    def optimize(
        strategy_cls: type[Strategy],
        base_params: dict[str, Any],
        param_grid: dict[str, list[Any]],
        bars: list[Bar],
        initial_capital: str = "100000",
        fee_model: str = "simple",
        slippage_model: str = "none",
        metric: str = "sharpe_ratio",
        max_runs: int = 200,
    ) -> dict[str, Any]:
        best_params: dict[str, Any] | None = None
        best_value: Decimal | None = None
        best_result: BacktestResult | None = None
        runs = 0

        keys = sorted(param_grid)
        values = [param_grid[k] for k in keys]

        for combo in _product(values):
            params = {**base_params, **dict(zip(keys, combo))}
            try:
                engine = BacktestEngine(
                    bars=bars,
                    strategy_cls=strategy_cls,
                    params=params,
                    initial_capital=initial_capital,
                    fee_model=fee_model,
                    slippage_model=slippage_model,
                )
                result = engine.run()
            except Exception as exc:  # noqa: BLE001
                logger.warning("backtest_optimize_error", params=params, error=str(exc)[:200])
                continue

            raw = result.metrics.get(metric)
            if raw is None:
                continue
            try:
                numeric = Decimal(str(raw).rstrip("%"))
            except Exception:
                continue

            is_better = _is_better_metric(metric, numeric, best_value)
            if is_better:
                best_value = numeric
                best_params = params
                best_result = result

            runs += 1
            if runs >= max_runs:
                break

        return {
            "best_params": best_params,
            "best_metric": metric,
            "best_metric_value": str(best_value) if best_value is not None else None,
            "runs": runs,
            "best_result": best_result,
        }

    # ── context ─────────────────────────────────────────────────────

    def _context(self, idx: int, state: dict[str, Any], position: BacktestPosition | None, bar: Bar) -> StrategyContext:
        registry = self._registry()

        def kline_provider(sym: str, period: str, count: int) -> list[Bar]:
            return list(self.bars[max(0, idx - count):idx])

        def ticker_provider(sym: str) -> Any:
            return type("T", (), {"last": str(bar.close)})()

        def indicator_provider(name: str, bars: list[Bar], params: dict[str, Any]) -> list[float | None]:
            return registry.compute(name, bars, params)

        def position_provider(sym: str) -> Any:
            if position is None or position.symbol != sym:
                return None
            return type("P", (), {"quantity": str(position.quantity)})()

        def cash_provider() -> Decimal:
            return state["cash"]

        def portfolio_provider() -> Decimal:
            pos = state.get("_position")
            return state["cash"] + (pos.quantity * bar.close if pos is not None else Decimal("0"))

        return StrategyContext(
            strategy_id=self.strategy.meta.kind,
            kline_provider=kline_provider,
            ticker_provider=ticker_provider,
            indicator_provider=indicator_provider,
            position_provider=position_provider,
            cash_provider=cash_provider,
            portfolio_provider=portfolio_provider,
            clock=lambda: datetime.fromtimestamp(bar.open_time / 1000, tz=timezone.utc),
            state_store=state.setdefault("strategy_state", {}),
        )

    @staticmethod
    def _registry() -> Any:
        from app.indicators.registry import default_indicator_registry
        return default_indicator_registry()

    # ── signal processing ───────────────────────────────────────────

    def _apply_signal(self, signal: Signal, bar: Bar, state: dict[str, Any]) -> None:
        st = signal.type
        pos = state.get("_position")

        if st in (SignalType.CLOSE_LONG, SignalType.REDUCE_LONG):
            if pos is None or pos.symbol != signal.symbol:
                return
            qty = self._resolve_exit_qty(signal, pos)
            if qty <= 0:
                return
            exec_price = self.slippage_fn.apply("sell", bar.close, bar)
            closeout = self._reduce_position(pos, qty, exec_price, bar.open_time, "signal")
            state["cash"] = state["cash"] + closeout.net_pnl + closeout.entry_price * closeout.quantity
            if pos.quantity <= Decimal("0"):
                state.pop("_position", None)
            return

        if st in (SignalType.STOP_LOSS, SignalType.TAKE_PROFIT):
            if pos is not None and pos.symbol == signal.symbol and signal.trigger_price is not None:
                if st == SignalType.STOP_LOSS:
                    pos.stop_loss = signal.trigger_price
                else:
                    pos.take_profit = signal.trigger_price
            return

        if st in (SignalType.OPEN_LONG, SignalType.ADD_LONG):
            if signal.symbol != self.symbol:
                return
            ctx = self._context(0, state, pos, bar)  # idx unused by DefaultSizer
            qty = self.sizer_cls().size(signal, ctx, bar.close)
            if qty <= 0:
                return
            exec_price = self.slippage_fn.apply("buy", bar.close, bar)
            self._open_position(state, signal.symbol, qty, exec_price)
            return

    def _open_position(self, state: dict[str, Any], symbol: str, qty: Decimal, exec_price: Decimal) -> None:
        fee = self.fee_fn(qty, exec_price, is_maker=False)
        cost = qty * exec_price + fee
        cash = state["cash"]
        if cost > cash:
            return

        pos = state.get("_position")
        if pos is not None and pos.symbol == symbol:
            total_qty = pos.quantity + qty
            new_entry = (pos.entry_price * pos.quantity + exec_price * qty) / total_qty
            pos.quantity = total_qty
            pos.entry_price = new_entry
            pos.entry_fee = pos.entry_fee + fee
        else:
            state["_position"] = BacktestPosition(
                symbol=symbol,
                quantity=qty,
                entry_price=exec_price,
                entry_time=0,
                entry_fee=fee,
            )
        state["cash"] = cash - cost

    def _reduce_position(self, position: BacktestPosition, qty: Decimal, exec_price: Decimal, exit_time: int, reason: str) -> BacktestTrade:
        fee = self.fee_fn(qty, exec_price, is_maker=False)
        proceeds = qty * exec_price - fee
        cost_basis = position.entry_price * qty
        gross_pnl = proceeds - cost_basis
        net_pnl = gross_pnl
        return_pct = (net_pnl / cost_basis) if cost_basis > 0 else Decimal("0")

        position.quantity -= qty
        position.entry_fee = position.entry_fee + fee

        return BacktestTrade(
            entry_time=position.entry_time,
            exit_time=exit_time,
            symbol=position.symbol,
            side="buy",
            quantity=qty,
            entry_price=position.entry_price,
            exit_price=exec_price,
            gross_pnl=gross_pnl,
            fee_paid=fee,
            net_pnl=net_pnl,
            return_pct=return_pct,
            exit_reason=reason,
        )

    def _close_position(self, position: BacktestPosition, exec_price: Decimal, exit_time: int, reason: str) -> BacktestTrade:
        return self._reduce_position(position, position.quantity, exec_price, exit_time, reason)

    def _check_stops(self, position: BacktestPosition, bar: Bar) -> BacktestTrade | None:
        if position.stop_loss is not None and bar.low <= position.stop_loss:
            fill = min(position.stop_loss, bar.open)
            return self._close_position(position, fill, bar.open_time, "stop_loss")
        if position.take_profit is not None and bar.high >= position.take_profit:
            fill = max(position.take_profit, bar.open)
            return self._close_position(position, fill, bar.open_time, "take_profit")
        return None

    @staticmethod
    def _resolve_exit_qty(signal: Signal, position: BacktestPosition) -> Decimal:
        if signal.quantity is not None:
            return min(signal.quantity, position.quantity)
        if signal.position_pct is not None:
            return (position.quantity * Decimal(str(signal.position_pct))).quantize(Decimal("0.00000001"))
        return position.quantity

    # ── metrics ─────────────────────────────────────────────────────

    def _metrics(self, trades, equity_curve, final_equity, max_dd) -> dict[str, Any]:
        initial = self.initial_capital
        net_profit = final_equity - initial
        total_return = ((final_equity - initial) / initial) if initial > 0 else Decimal("0")

        returns: list[Decimal] = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1][1]
            curr = equity_curve[i][1]
            if prev > 0:
                returns.append((curr - prev) / prev)

        sharpe = Decimal("0")
        if len(returns) > 1:
            avg = sum(returns) / len(returns)
            variance = sum((r - avg) ** 2 for r in returns) / (len(returns) - 1)
            std = variance ** Decimal("0.5")
            if std > 0:
                bars_per_year = self._bars_per_year()
                sharpe = (avg / std) * (Decimal(str(bars_per_year)) ** Decimal("0.5"))

        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]
        win_rate = Decimal(str(len(wins))) / Decimal(str(len(trades))) if trades else Decimal("0")
        gross_profit = sum(t.net_pnl for t in wins)
        gross_loss = abs(sum(t.net_pnl for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else Decimal("999999")

        return {
            "net_profit": str(net_profit.quantize(Decimal("0.01"))),
            "final_equity": str(final_equity.quantize(Decimal("0.01"))),
            "total_return_pct": f"{(total_return * 100).quantize(Decimal('0.01'))}%",
            "sharpe_ratio": str(sharpe.quantize(Decimal("0.01"))),
            "max_drawdown": f"-{(max_dd * 100).quantize(Decimal('0.0001'))}%",
            "win_rate": f"{(win_rate * 100).quantize(Decimal('0.01'))}%",
            "profit_factor": str(profit_factor.quantize(Decimal("0.01"))),
            "total_trades": len(trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "avg_trade_pnl": str((net_profit / len(trades)).quantize(Decimal("0.01"))) if trades else "0",
            "avg_win": str((gross_profit / len(wins)).quantize(Decimal("0.01"))) if wins else "0",
            "avg_loss": str((gross_loss / len(losses)).quantize(Decimal("0.01"))) if losses else "0",
            "largest_win": str(max((t.net_pnl for t in wins), default=Decimal("0")).quantize(Decimal("0.01"))),
            "largest_loss": str(min((t.net_pnl for t in losses), default=Decimal("0")).quantize(Decimal("0.01"))),
        }

    def _bars_per_year(self) -> float:
        if len(self.bars) < 2:
            return 252.0 * 24.0 * 60.0
        total_ms = self.bars[-1].open_time - self.bars[0].open_time
        if total_ms <= 0:
            return 252.0 * 24.0 * 60.0
        avg_ms = total_ms / (len(self.bars) - 1)
        if avg_ms <= 0:
            return 252.0 * 24.0 * 60.0
        return 365.0 * 24.0 * 3600.0 * 1000.0 / avg_ms


def _product(lists: list[list[Any]]) -> list[tuple[Any, ...]]:
    if not lists:
        return [()]
    head, *tail = lists
    rest = _product(tail) if tail else [()]
    out: list[tuple[Any, ...]] = []
    for item in head:
        for combo in rest:
            out.append((item,) + combo if combo else (item,))
    return out


def _is_better_metric(metric: str, value: Decimal, current_best: Decimal | None) -> bool:
    if current_best is None:
        return True
    if metric in ("max_drawdown",):
        return value < current_best
    return value > current_best
