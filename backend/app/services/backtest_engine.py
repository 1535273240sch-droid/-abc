"""Bar-by-bar backtest engine for the pluggable strategy framework.

Produces realistic fills (Maker/Taker fees + fixed/percentage/ATR dynamic slippage + funding rates),
an equity curve, and the complete quantitative performance metrics suite:

- net profit / final equity / total return pct
- CAGR (Compound Annual Growth Rate)
- max drawdown & drawdown duration
- Sharpe ratio (annualized)
- Sortino ratio (annualized downside deviation)
- Calmar ratio (CAGR / MaxDD)
- win rate / profit factor / payoff ratio
- average win / loss / trade pnl
- strategy parameter grid search optimizer
"""

from __future__ import annotations

import json
import re
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
    """Configurable trading fee model and perpetual funding rate engine."""

    def __init__(
        self,
        maker_rate: Decimal = Decimal("0.0002"),
        taker_rate: Decimal = Decimal("0.0004"),
        funding_rate: Decimal = Decimal("0.0001"),
        enable_funding: bool = True,
    ):
        self.maker_rate = maker_rate
        self.taker_rate = taker_rate
        self.funding_rate = funding_rate
        self.enable_funding = enable_funding

    def calculate(self, qty: Decimal, price: Decimal, is_maker: bool = False) -> Decimal:
        rate = self.maker_rate if is_maker else self.taker_rate
        return (qty * price * rate).quantize(Decimal("0.00000001"))

    def __call__(self, qty: Decimal, price: Decimal, is_maker: bool = False) -> Decimal:
        return self.calculate(qty, price, is_maker)

    def funding_payment(
        self,
        quantity: Decimal,
        price: Decimal,
        funding_rate: Decimal | None = None,
        is_long: bool = True,
    ) -> Decimal:
        """Calculate perpetual funding fee payment.
        Positive value: cost paid (deducted from cash).
        Negative value: income received (added to cash).
        """
        fr = funding_rate if funding_rate is not None else self.funding_rate
        notional = quantity * price
        if is_long:
            return (notional * fr).quantize(Decimal("0.00000001"))
        else:
            return (-notional * fr).quantize(Decimal("0.00000001"))

    @classmethod
    def resolve(cls, model: str | Any, **kwargs: Any) -> "FeeModel":
        if isinstance(model, FeeModel):
            return model
        m = (str(model) if model else "simple").lower().strip()
        if m in ("none", "zero", "0"):
            return cls(
                maker_rate=Decimal("0"),
                taker_rate=Decimal("0"),
                funding_rate=Decimal("0"),
                enable_funding=False,
            )
        if m == "simple":
            rate = Decimal(str(kwargs.get("fee_bps", 10))) / Decimal("10000")
            return cls(maker_rate=rate, taker_rate=rate)
        if m == "tiered":
            maker = Decimal(str(kwargs.get("maker_bps", 8))) / Decimal("10000")
            taker = Decimal(str(kwargs.get("taker_bps", 10))) / Decimal("10000")
            return cls(maker_rate=maker, taker_rate=taker)

        # Regex match: e.g. maker_0.02pct_taker_0.04pct
        match = re.search(r"maker_([0-9.]+)pct_taker_([0-9.]+)pct", m)
        if match:
            maker = Decimal(match.group(1)) / Decimal("100")
            taker = Decimal(match.group(2)) / Decimal("100")
            return cls(maker_rate=maker, taker_rate=taker)

        match_single = re.search(r"([0-9.]+)pct", m)
        if match_single:
            rate = Decimal(match_single.group(1)) / Decimal("100")
            return cls(maker_rate=rate, taker_rate=rate)

        try:
            rate = Decimal(m)
            return cls(maker_rate=rate, taker_rate=rate)
        except Exception:
            return cls(maker_rate=Decimal("0.0002"), taker_rate=Decimal("0.0004"))


class SlippageModel:
    """Execution price slippage model supporting Fixed, Percentage, and ATR Dynamic modes."""

    def __init__(
        self,
        mode: str = "none",
        fixed_amount: Decimal = Decimal("0"),
        pct_rate: Decimal = Decimal("0"),
        atr_mult: Decimal = Decimal("0.05"),
    ):
        self.mode = mode
        self.fixed_amount = fixed_amount
        self.pct_rate = pct_rate
        self.atr_mult = atr_mult

    def apply(self, side: str, price: Decimal, bar: Bar, atr: Decimal | None = None) -> Decimal:
        s = side.lower().strip()
        if self.mode == "none":
            return price
        elif self.mode == "fixed_price":
            if s == "buy":
                return price + self.fixed_amount
            else:
                return max(Decimal("0.00000001"), price - self.fixed_amount)
        elif self.mode == "percentage":
            if s == "buy":
                return price * (Decimal("1") + self.pct_rate)
            else:
                return max(Decimal("0.00000001"), price * (Decimal("1") - self.pct_rate))
        elif self.mode in ("volatility", "atr", "dynamic"):
            if atr is not None and atr > Decimal("0"):
                slip = (atr * self.atr_mult).quantize(Decimal("0.00000001"))
            else:
                range_ = (bar.high - bar.low) if bar.high > bar.low else price * Decimal("0.001")
                slip = (range_ * self.atr_mult).quantize(Decimal("0.00000001"))
            if s == "buy":
                return price + slip
            else:
                return max(Decimal("0.00000001"), price - slip)
        return price

    def __call__(self, side: str, price: Decimal, bar: Bar, atr: Decimal | None = None) -> Decimal:
        return self.apply(side, price, bar, atr)

    @classmethod
    def resolve(cls, model: str | Any, **kwargs: Any) -> "SlippageModel":
        if isinstance(model, SlippageModel):
            return model
        m = (str(model) if model else "none").lower().strip()
        if m in ("none", "zero", "0"):
            return cls(mode="none")
        if m == "fixed_price":
            amount = Decimal(str(kwargs.get("slippage_price", 10)))
            return cls(mode="fixed_price", fixed_amount=amount)
        if m in ("volatility", "atr", "atr_dynamic", "atr14", "dynamic"):
            mult = Decimal(str(kwargs.get("atr_mult", 0.05)))
            return cls(mode="volatility", atr_mult=mult)

        # Regex match: e.g. conservative_1.5bps, 5bps, 0.02pct
        bps_match = re.search(r"([0-9.]+)bps", m)
        if bps_match:
            bps = Decimal(bps_match.group(1))
            return cls(mode="percentage", pct_rate=bps / Decimal("10000"))

        pct_match = re.search(r"([0-9.]+)pct", m)
        if pct_match:
            pct = Decimal(pct_match.group(1))
            return cls(mode="percentage", pct_rate=pct / Decimal("100"))

        if m == "fixed_bps":
            bps = Decimal(str(kwargs.get("slippage_bps", 5))) / Decimal("10000")
            return cls(mode="percentage", pct_rate=bps)

        try:
            rate = Decimal(m)
            return cls(mode="percentage", pct_rate=rate)
        except Exception:
            return cls(mode="none")


class BacktestEngine:
    """Deterministic bar-by-bar backtest driver for :class:`Strategy` subclasses."""

    def __init__(
        self,
        bars: list[Bar],
        strategy_cls: type[Strategy],
        params: dict[str, Any],
        initial_capital: str = "100000",
        fee_model: str | FeeModel = "simple",
        slippage_model: str | SlippageModel = "none",
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
        last_funding_bar_time = 0

        for idx, bar in enumerate(self.bars):
            position = state.get("_position")

            # Perpetual 8-hour funding rate settlement (00:00, 08:00, 16:00 UTC)
            if self.fee_fn.enable_funding and position is not None:
                # 8h cycle: 28,800,000 ms
                if bar.open_time - last_funding_bar_time >= 28_800_000 or (bar.open_time % 28_800_000 < 3_600_000 and bar.open_time != last_funding_bar_time):
                    funding_cost = self.fee_fn.funding_payment(position.quantity, bar.close, is_long=True)
                    state["cash"] = state["cash"] - funding_cost
                    last_funding_bar_time = bar.open_time

            if idx >= warmup:
                ctx = self._context(idx, state, position, bar)
                try:
                    signals = strategy.on_bar(ctx, bar)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("backtest_signal_error", idx=idx, error=str(exc)[:200])
                    signals = []

                if not isinstance(signals, list):
                    signals = []

                # Intra-bar risk management (stop loss / take profit) before processing new signals
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
                    self._apply_signal(signal, bar, state, trades)
                    position = state.get("_position")

            # Mark-to-market at bar close
            equity = state["cash"] + (
                position.quantity * bar.close if position is not None else Decimal("0")
            )
            hwm = max(hwm, equity)
            dd = (hwm - equity) / hwm if hwm > Decimal("0") else Decimal("0")
            max_dd = max(max_dd, dd)
            equity_curve.append((bar.open_time, equity))

        # Close any open position at the last bar's close
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
        fee_model: str | FeeModel = "simple",
        slippage_model: str | SlippageModel = "none",
        metric: str = "sharpe_ratio",
        max_runs: int = 200,
    ) -> dict[str, Any]:
        """Cartesian product grid search optimization over parameter space."""
        if not param_grid:
            raise QuantError("VALIDATION_ERROR", "param_grid must not be empty", status_code=400)

        keys = sorted(param_grid)
        values = [param_grid[k] for k in keys]
        combinations = _product(values)

        results: list[dict[str, Any]] = []
        best_params: dict[str, Any] | None = None
        best_value: Decimal | None = None
        best_result: BacktestResult | None = None
        runs = 0

        for combo in combinations:
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
                if metric == "max_drawdown":
                    numeric = Decimal(str(raw).rstrip("%").lstrip("-"))
                else:
                    numeric = Decimal(str(raw).rstrip("%"))
            except Exception:
                continue

            is_better = _is_better_metric(metric, numeric, best_value)
            if is_better:
                best_value = numeric
                best_params = params
                best_result = result

            results.append({
                "params": params,
                "metric": metric,
                "metric_value": str(raw),
                "numeric_metric": float(numeric),
                "total_trades": result.total_trades,
                "net_profit": result.net_profit,
                "win_rate": result.win_rate,
                "max_drawdown": result.max_drawdown,
                "sharpe_ratio": result.sharpe_ratio,
            })

            runs += 1
            if runs >= max_runs:
                break

        # Sort results
        reverse_sort = metric not in ("max_drawdown",)
        results.sort(key=lambda r: r["numeric_metric"], reverse=reverse_sort)

        return {
            "best_params": best_params,
            "best_metric": metric,
            "best_metric_value": str(best_value) if best_value is not None else None,
            "runs": runs,
            "total_combinations": len(combinations),
            "results": results,
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

    def _apply_signal(self, signal: Signal, bar: Bar, state: dict[str, Any], trades: list[BacktestTrade]) -> None:
        st = signal.type
        pos = state.get("_position")

        if st in (SignalType.CLOSE_LONG, SignalType.REDUCE_LONG):
            if pos is None or pos.symbol != signal.symbol:
                return
            qty = self._resolve_exit_qty(signal, pos)
            if qty <= Decimal("0"):
                return
            exec_price = self.slippage_fn.apply("sell", bar.close, bar)
            closeout = self._reduce_position(pos, qty, exec_price, bar.open_time, "signal")
            trades.append(closeout)
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
            ctx = self._context(0, state, pos, bar)
            qty = self.sizer_cls().size(signal, ctx, bar.close)
            if qty <= Decimal("0"):
                return
            exec_price = self.slippage_fn.apply("buy", bar.close, bar)
            self._open_position(state, signal.symbol, qty, exec_price)
            return

    def _open_position(self, state: dict[str, Any], symbol: str, qty: Decimal, exec_price: Decimal) -> None:
        fee = self.fee_fn.calculate(qty, exec_price, is_maker=False)
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
        fee = self.fee_fn.calculate(qty, exec_price, is_maker=False)
        proceeds = qty * exec_price - fee
        cost_basis = position.entry_price * qty
        gross_pnl = proceeds - cost_basis
        net_pnl = gross_pnl
        return_pct = (net_pnl / cost_basis) if cost_basis > Decimal("0") else Decimal("0")

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

    def _metrics(
        self,
        trades: list[BacktestTrade],
        equity_curve: list[tuple[int, Decimal]],
        final_equity: Decimal,
        max_dd: Decimal,
    ) -> dict[str, Any]:
        initial = self.initial_capital
        net_profit = final_equity - initial
        total_return = ((final_equity - initial) / initial) if initial > Decimal("0") else Decimal("0")

        # Period returns
        returns: list[Decimal] = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1][1]
            curr = equity_curve[i][1]
            if prev > Decimal("0"):
                returns.append((curr - prev) / prev)

        N = len(equity_curve)
        bars_per_year = Decimal(str(self._bars_per_year()))

        # CAGR
        cagr = Decimal("0")
        if N > 0 and initial > Decimal("0"):
            one_plus_r = final_equity / initial
            if one_plus_r <= Decimal("0"):
                cagr = Decimal("-1.0")
            else:
                try:
                    exp = float(bars_per_year) / float(N)
                    cagr_val = float(one_plus_r) ** exp - 1.0
                    cagr = Decimal(str(cagr_val))
                except Exception:
                    cagr = Decimal("-1.0") if one_plus_r <= 0 else Decimal("0")

        # Sharpe ratio
        sharpe = Decimal("0")
        if len(returns) > 1:
            avg = sum(returns) / Decimal(str(len(returns)))
            variance = sum((r - avg) ** 2 for r in returns) / Decimal(str(len(returns) - 1))
            std = variance ** Decimal("0.5")
            if std > Decimal("1e-9"):
                sharpe = (avg / std) * (bars_per_year ** Decimal("0.5"))

        # Sortino ratio (downside deviation)
        sortino = Decimal("0")
        if len(returns) > 0:
            avg = sum(returns) / Decimal(str(len(returns)))
            downside_sq = [r ** 2 for r in returns if r < 0]
            if downside_sq:
                downside_std = (sum(downside_sq) / Decimal(str(len(returns)))) ** Decimal("0.5")
                if downside_std > Decimal("1e-9"):
                    sortino = (avg / downside_std) * (bars_per_year ** Decimal("0.5"))
                else:
                    sortino = Decimal("999.0") if avg > 0 else Decimal("0")
            else:
                sortino = Decimal("999.0") if avg > 0 else Decimal("0")

        # Calmar ratio
        calmar = Decimal("0")
        if max_dd > Decimal("1e-9"):
            calmar = cagr / max_dd
        else:
            calmar = Decimal("999.0") if cagr > 0 else Decimal("0")

        # Max Drawdown duration
        dd_duration = 0
        curr_dd_dur = 0
        peak = initial
        for _, eq in equity_curve:
            if eq >= peak:
                peak = eq
                curr_dd_dur = 0
            else:
                curr_dd_dur += 1
                if curr_dd_dur > dd_duration:
                    dd_duration = curr_dd_dur

        # Trades stats
        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]
        win_rate = Decimal(str(len(wins))) / Decimal(str(len(trades))) if trades else Decimal("0")
        gross_profit = sum((t.net_pnl for t in wins), Decimal("0"))
        gross_loss = abs(sum((t.net_pnl for t in losses), Decimal("0")))

        # Profit Factor
        if gross_loss > Decimal("0"):
            profit_factor = gross_profit / gross_loss
        elif gross_profit > Decimal("0"):
            profit_factor = Decimal("999.0")
        else:
            profit_factor = Decimal("0")

        # Payoff Ratio (Average Win / Average Loss)
        avg_win_val = (gross_profit / Decimal(str(len(wins)))) if wins else Decimal("0")
        avg_loss_val = (gross_loss / Decimal(str(len(losses)))) if losses else Decimal("0")
        if avg_loss_val > Decimal("0"):
            payoff_ratio = avg_win_val / avg_loss_val
        elif avg_win_val > Decimal("0"):
            payoff_ratio = Decimal("999.0")
        else:
            payoff_ratio = Decimal("0")

        bounded_max_dd = min(Decimal("1.0"), max(Decimal("0.0"), max_dd))

        return {
            "net_profit": str(net_profit.quantize(Decimal("0.01"))),
            "final_equity": str(final_equity.quantize(Decimal("0.01"))),
            "total_return_pct": f"{(total_return * 100).quantize(Decimal('0.01'))}%",
            "cagr": float(cagr.quantize(Decimal("0.0001"))),
            "sharpe_ratio": str(sharpe.quantize(Decimal("0.01"))),
            "sortino_ratio": float(sortino.quantize(Decimal("0.01"))),
            "calmar_ratio": float(calmar.quantize(Decimal("0.01"))),
            "max_drawdown": f"-{(bounded_max_dd * 100).quantize(Decimal('0.0001'))}%",
            "drawdown_duration": dd_duration,
            "win_rate": f"{(win_rate * 100).quantize(Decimal('0.01'))}%",
            "profit_factor": str(profit_factor.quantize(Decimal("0.01"))),
            "payoff_ratio": float(payoff_ratio.quantize(Decimal("0.01"))),
            "total_trades": len(trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "avg_trade_pnl": str((net_profit / Decimal(str(len(trades)))).quantize(Decimal("0.01"))) if trades else "0",
            "avg_win": str(avg_win_val.quantize(Decimal("0.01"))),
            "avg_loss": str(avg_loss_val.quantize(Decimal("0.01"))),
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
