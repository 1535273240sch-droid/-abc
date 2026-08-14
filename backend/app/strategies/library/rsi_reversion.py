"""RSI mean-reversion strategy: buy oversold dips, sell overbought rallies.

Demonstrates a different paradigm from the trend-following dual_ma:
oscillator-based entries, staged exits (partial profit-taking), and a
cooldown timer using strategy state.
"""

from app.strategies.base import DataRequirement, ParamSpec, Strategy, StrategyMeta
from app.strategies.registry import register_strategy
from app.strategies.signal import Bar, Signal, SignalType


@register_strategy
class RsiReversionStrategy(Strategy):

    meta = StrategyMeta(
        kind="rsi_reversion",
        name="RSI 均值回归策略",
        version="1.0.0",
        description="RSI 超卖买入、超买分批止盈，带冷却期防止频繁交易",
        params=(
            ParamSpec("rsi_period", int, 14, min_value=5, max_value=50, description="RSI 周期"),
            ParamSpec("oversold", float, 30.0, min_value=5, max_value=45, description="超卖阈值"),
            ParamSpec("overbought", float, 70.0, min_value=55, max_value=95, description="超买阈值"),
            ParamSpec("cash_pct", float, 0.25, min_value=0.05, max_value=1.0, description="单次买入资金比例"),
            ParamSpec("first_exit_pct", float, 0.5, min_value=0.1, max_value=1.0, description="首次止盈仓位比例"),
            ParamSpec("cooldown_bars", int, 5, min_value=0, max_value=100, description="平仓后冷却K线数"),
            ParamSpec("kline_period", str, "1h", description="K线周期"),
        ),
        data_requirements=frozenset({DataRequirement.KLINE_1H}),
        warmup_bars=100,
        symbols=("ETHUSDT",),
    )

    def on_init(self, ctx) -> None:
        ctx.state.setdefault("cooldown", 0)
        ctx.state.setdefault("took_first_profit", False)

    def on_bar(self, ctx, bar: Bar) -> list[Signal]:
        period = self.p["kline_period"]
        rsi = ctx.indicator(
            "rsi", bar.symbol, period=period,
            count=max(self.p["rsi_period"] * 4, 60),
            length=self.p["rsi_period"],
        )
        if rsi is None:
            return []

        # cooldown countdown after each exit
        if ctx.state["cooldown"] > 0:
            ctx.state["cooldown"] -= 1
            return []

        pos = ctx.position(bar.symbol)
        signals: list[Signal] = []

        # ── entry: oversold and flat ──
        if pos is None and rsi < self.p["oversold"]:
            ctx.state["took_first_profit"] = False
            signals.append(Signal(
                type=SignalType.OPEN_LONG,
                symbol=bar.symbol,
                cash_pct=self.p["cash_pct"],
                reason=f"RSI超卖买入: RSI{self.p['rsi_period']}={rsi:.1f} < {self.p['oversold']}",
                tag="rsi_oversold",
            ))
            return signals

        if pos is None:
            return []

        # ── staged exit: first target ──
        mid = (self.p["oversold"] + self.p["overbought"]) / 2
        if not ctx.state["took_first_profit"] and rsi > mid:
            ctx.state["took_first_profit"] = True
            signals.append(Signal(
                type=SignalType.REDUCE_LONG,
                symbol=bar.symbol,
                position_pct=self.p["first_exit_pct"],
                reason=f"RSI回归中轴，首批止盈{self.p['first_exit_pct']*100:.0f}%: RSI={rsi:.1f}",
                tag="rsi_first_profit",
            ))
            return signals

        # ── final exit: overbought ──
        if rsi > self.p["overbought"]:
            signals.append(Signal(
                type=SignalType.CLOSE_LONG,
                symbol=bar.symbol,
                position_pct=1.0,
                reason=f"RSI超买清仓: RSI={rsi:.1f} > {self.p['overbought']}",
                tag="rsi_overbought",
            ))
            ctx.state["cooldown"] = self.p["cooldown_bars"]
            ctx.state["took_first_profit"] = False

        return signals
