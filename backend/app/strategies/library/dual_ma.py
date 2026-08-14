"""Dual moving-average trend strategy with ATR trailing stop.

Reference implementation showing the framework's full capabilities:
declarative params, indicator access, private state, partial exits,
and volatility-based stops — with zero data-plumbing code.
"""

from app.strategies.base import DataRequirement, ParamSpec, Strategy, StrategyMeta
from app.strategies.registry import register_strategy
from app.strategies.signal import Bar, Signal, SignalType


@register_strategy
class DualMaStrategy(Strategy):

    meta = StrategyMeta(
        kind="dual_ma",
        name="双均线趋势策略",
        version="1.0.0",
        description="快线上穿慢线开多，下穿平仓；ATR 移动止损保护持仓",
        params=(
            ParamSpec("fast_period", int, 5, min_value=2, max_value=120, description="快线周期"),
            ParamSpec("slow_period", int, 20, min_value=5, max_value=500, description="慢线周期"),
            ParamSpec("cash_pct", float, 0.3, min_value=0.05, max_value=1.0, description="单次开仓资金比例"),
            ParamSpec("atr_stop_mult", float, 2.0, min_value=0.5, max_value=10.0, description="ATR 止损倍数"),
            ParamSpec("kline_period", str, "1h", description="K线周期: 1m/5m/15m/1h/4h/1d"),
        ),
        data_requirements=frozenset({DataRequirement.KLINE_1H}),
        warmup_bars=500,
        symbols=("BTCUSDT",),
    )

    def on_init(self, ctx) -> None:
        ctx.state.setdefault("entry_price", None)
        ctx.state.setdefault("highest_since_entry", None)

    def on_bar(self, ctx, bar: Bar) -> list[Signal]:
        period = self.p["kline_period"]
        count = max(self.p["slow_period"] * 2, 60)

        fast = ctx.indicator("sma", bar.symbol, period=period, count=count, length=self.p["fast_period"])
        slow = ctx.indicator("sma", bar.symbol, period=period, count=count, length=self.p["slow_period"])
        atr = ctx.indicator("atr", bar.symbol, period=period, count=count, length=14)

        if fast is None or slow is None or atr is None:
            return []  # warmup not complete

        pos = ctx.position(bar.symbol)
        signals: list[Signal] = []

        # ── entry: golden cross ──
        if pos is None and fast > slow:
            ctx.state["entry_price"] = float(bar.close)
            ctx.state["highest_since_entry"] = float(bar.close)
            signals.append(Signal(
                type=SignalType.OPEN_LONG,
                symbol=bar.symbol,
                cash_pct=self.p["cash_pct"],
                reason=f"金叉开多: MA{self.p['fast_period']}={fast:.2f} > MA{self.p['slow_period']}={slow:.2f}",
                tag="golden_cross",
            ))
            return signals

        if pos is None:
            return []

        # ── in position: maintain trailing anchor ──
        close = float(bar.close)
        prev_high = ctx.state.get("highest_since_entry") or close
        ctx.state["highest_since_entry"] = max(prev_high, close)

        # ATR trailing stop from the highest close since entry
        stop = ctx.state["highest_since_entry"] - atr * self.p["atr_stop_mult"]
        if close < stop:
            signals.append(Signal(
                type=SignalType.CLOSE_LONG,
                symbol=bar.symbol,
                position_pct=1.0,
                reason=f"ATR移动止损: 现价{close:.2f} 跌破止损线{stop:.2f} (峰值{ctx.state['highest_since_entry']:.2f} - {self.p['atr_stop_mult']}×ATR{atr:.2f})",
                tag="atr_trailing_stop",
            ))
            ctx.state["entry_price"] = None
            ctx.state["highest_since_entry"] = None
            return signals

        # ── exit: death cross ──
        if fast < slow:
            signals.append(Signal(
                type=SignalType.CLOSE_LONG,
                symbol=bar.symbol,
                position_pct=1.0,
                reason=f"死叉平仓: MA{self.p['fast_period']}={fast:.2f} < MA{self.p['slow_period']}={slow:.2f}",
                tag="death_cross",
            ))
            ctx.state["entry_price"] = None
            ctx.state["highest_since_entry"] = None

        return signals
