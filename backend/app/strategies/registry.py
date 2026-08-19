"""Strategy registry: kind → Strategy class, with auto-discovery and built-in strategy mappings.

Strategies self-register via the ``@register_strategy`` decorator, or are
registered explicitly. ``autodiscover()`` imports every module under
``app.strategies.library`` so dropping a new file there is enough to make
the strategy available — true plug-and-play.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

from app.strategies.base import DataRequirement, ParamSpec, Strategy, StrategyMeta
from app.strategies.signal import Bar, Signal, SignalType


class StrategyRegistry:
    def __init__(self) -> None:
        self._classes: dict[str, type[Strategy]] = {}
        self._discovered: bool = False

    def register(self, cls: type[Strategy]) -> type[Strategy]:
        kind = cls.meta.kind
        if not kind:
            raise ValueError(f"{cls.__name__}.meta.kind must be non-empty")
        self._classes[kind] = cls
        return cls

    def _ensure_discovered(self) -> None:
        if not self._discovered:
            self._discovered = True
            autodiscover()

    def get(self, kind: str) -> type[Strategy] | None:
        self._ensure_discovered()
        k = kind.strip().lower()
        if k in self._classes:
            return self._classes[k]
        # Check standard aliases
        alias_map = {
            "trend": "trend",
            "trend_following": "trend",
            "trend-btc": "trend",
            "dual_ma": "dual_ma",
            "arbitrage": "arbitrage",
            "arb": "arbitrage",
            "arb-eth": "arbitrage",
            "rsi_reversion": "rsi_reversion",
            "mean_reversion": "rsi_reversion",
            "grid": "grid",
            "grid-bnb": "grid",
            "grid_trading": "grid",
        }
        target = alias_map.get(k)
        if target and target in self._classes:
            return self._classes[target]
        # Fallback search
        for name, cls in self._classes.items():
            if k in name or name in k:
                return cls
        return None

    def create(self, kind: str, params: dict[str, Any] | None = None) -> Strategy:
        cls = self.get(kind)
        if cls is None:
            raise KeyError(f"unknown strategy kind '{kind}', registered: {self.kinds()}")
        return cls(params)

    def kinds(self) -> list[str]:
        self._ensure_discovered()
        return sorted(self._classes)

    def catalog(self) -> list[dict[str, Any]]:
        """Metadata + param schema for every registered strategy."""
        self._ensure_discovered()
        out = []
        for kind in self.kinds():
            cls = self._classes[kind]
            meta: StrategyMeta = cls.meta
            out.append({
                "kind": meta.kind,
                "name": meta.name,
                "version": meta.version,
                "description": meta.description,
                "params": cls.params_schema(),
                "data_requirements": sorted(r.value for r in meta.data_requirements),
                "warmup_bars": meta.warmup_bars,
                "symbols": list(meta.symbols),
            })
        return out


# Module-level default registry shared by the app.
registry = StrategyRegistry()


def register_strategy(cls: type[Strategy]) -> type[Strategy]:
    """Decorator: @register_strategy on a Strategy subclass."""
    return registry.register(cls)


# ── Built-in Standard Strategies ──────────────────────────────────────

@register_strategy
class TrendFollowingStrategy(Strategy):
    """Standard Dual-EMA / MA Trend Following Strategy with ATR dynamic stop."""

    meta = StrategyMeta(
        kind="trend",
        name="趋势跟踪策略",
        version="1.0.0",
        description="基于EMA均线交叉与ATR动态止损的趋势跟踪策略",
        params=(
            ParamSpec("ema_fast", int, 5, min_value=2, max_value=120, description="EMA快线周期"),
            ParamSpec("ema_slow", int, 15, min_value=5, max_value=500, description="EMA慢线周期"),
            ParamSpec("fast_period", int, 5, min_value=2, max_value=120, description="快线周期"),
            ParamSpec("slow_period", int, 15, min_value=5, max_value=500, description="慢线周期"),
            ParamSpec("cash_pct", float, 0.3, min_value=0.05, max_value=1.0, description="单次开仓资金比例"),
            ParamSpec("atr_stop_mult", float, 1.0, min_value=0.1, max_value=10.0, description="ATR 止损倍数"),
            ParamSpec("kline_period", str, "1h", description="K线周期"),
        ),
        data_requirements=frozenset({DataRequirement.KLINE_1H}),
        warmup_bars=20,
        symbols=("BTCUSDT",),
    )

    def on_init(self, ctx: Any) -> None:
        ctx.state.setdefault("entry_price", None)
        ctx.state.setdefault("highest_since_entry", None)

    def on_bar(self, ctx: Any, bar: Bar) -> list[Signal]:
        period = self.p.get("kline_period", "1h")
        f = self.p.get("ema_fast") or self.p.get("fast_period") or 5
        s = self.p.get("ema_slow") or self.p.get("slow_period") or 15
        count = max(int(s) * 2, 50)

        fast = ctx.indicator("ema", bar.symbol, period=period, count=count, length=int(f))
        slow = ctx.indicator("ema", bar.symbol, period=period, count=count, length=int(s))
        atr = ctx.indicator("atr", bar.symbol, period=period, count=count, length=14)

        if fast is None or slow is None:
            return []

        pos = ctx.position(bar.symbol)
        signals: list[Signal] = []

        if pos is None and fast > slow:
            ctx.state["entry_price"] = float(bar.close)
            ctx.state["highest_since_entry"] = float(bar.close)
            signals.append(Signal(
                type=SignalType.OPEN_LONG,
                symbol=bar.symbol,
                cash_pct=self.p.get("cash_pct", 0.3),
                reason=f"均线金叉开多: EMA{f}={fast:.2f} > EMA{s}={slow:.2f}",
                tag="golden_cross",
            ))
            return signals

        if pos is None:
            return []

        close = float(bar.close)
        prev_high = ctx.state.get("highest_since_entry") or close
        ctx.state["highest_since_entry"] = max(prev_high, close)

        atr_mult = self.p.get("atr_stop_mult", 1.0)
        if atr is not None and atr_mult:
            stop = ctx.state["highest_since_entry"] - atr * atr_mult
            if close < stop:
                signals.append(Signal(
                    type=SignalType.CLOSE_LONG,
                    symbol=bar.symbol,
                    position_pct=1.0,
                    reason=f"ATR移动止损: 跌破 {stop:.2f}",
                    tag="atr_stop",
                ))
                ctx.state["entry_price"] = None
                ctx.state["highest_since_entry"] = None
                return signals

        if fast < slow:
            signals.append(Signal(
                type=SignalType.CLOSE_LONG,
                symbol=bar.symbol,
                position_pct=1.0,
                reason=f"均线死叉平仓: EMA{f}={fast:.2f} < EMA{s}={slow:.2f}",
                tag="death_cross",
            ))
            ctx.state["entry_price"] = None
            ctx.state["highest_since_entry"] = None

        return signals


@register_strategy
class ArbitrageStrategy(Strategy):
    """Mean-reversion & statistical arbitrage strategy using Bollinger Bands."""

    meta = StrategyMeta(
        kind="arbitrage",
        name="统计套利策略",
        version="1.0.0",
        description="基于布林带与价差均值回归的套利策略",
        params=(
            ParamSpec("min_spread", float, 0.001, description="最小价差阈值"),
            ParamSpec("bollinger_period", int, 20, min_value=5, max_value=100, description="布林带周期"),
            ParamSpec("cash_pct", float, 0.3, min_value=0.05, max_value=1.0, description="单次开仓资金比例"),
            ParamSpec("kline_period", str, "1h", description="K线周期"),
        ),
        data_requirements=frozenset({DataRequirement.KLINE_1H}),
        warmup_bars=25,
        symbols=("ETHUSDT", "BTCUSDT"),
    )

    def on_init(self, ctx: Any) -> None:
        ctx.state.setdefault("in_position", False)

    def on_bar(self, ctx: Any, bar: Bar) -> list[Signal]:
        period = self.p.get("kline_period", "1h")
        b_period = int(self.p.get("bollinger_period", 20))
        lower = ctx.indicator("bollinger", bar.symbol, period=period, count=b_period * 2, length=b_period, band="lower")
        upper = ctx.indicator("bollinger", bar.symbol, period=period, count=b_period * 2, length=b_period, band="upper")
        mid = ctx.indicator("bollinger", bar.symbol, period=period, count=b_period * 2, length=b_period, band="mid")

        if lower is None or upper is None or mid is None:
            return []

        pos = ctx.position(bar.symbol)
        close = float(bar.close)
        signals: list[Signal] = []

        if pos is None and close <= lower:
            signals.append(Signal(
                type=SignalType.OPEN_LONG,
                symbol=bar.symbol,
                cash_pct=self.p.get("cash_pct", 0.3),
                reason=f"触及布林下轨开多: Price {close:.2f} <= Lower {lower:.2f}",
                tag="arb_open",
            ))
            return signals

        if pos is not None and (close >= mid or close >= upper):
            signals.append(Signal(
                type=SignalType.CLOSE_LONG,
                symbol=bar.symbol,
                position_pct=1.0,
                reason=f"回归布林中轨平仓: Price {close:.2f} >= Mid {mid:.2f}",
                tag="arb_close",
            ))

        return signals


@register_strategy
class GridStrategy(Strategy):
    """Interval grid trading strategy."""

    meta = StrategyMeta(
        kind="grid",
        name="网格交易策略",
        version="1.0.0",
        description="等间距分批挂单与区间套利网格策略",
        params=(
            ParamSpec("grid_levels", int, 10, min_value=2, max_value=100, description="网格层数"),
            ParamSpec("spread", float, 0.005, description="网格间距比例"),
            ParamSpec("cash_pct", float, 0.1, min_value=0.01, max_value=1.0, description="单网格资金比例"),
            ParamSpec("kline_period", str, "1h", description="K线周期"),
        ),
        data_requirements=frozenset({DataRequirement.KLINE_1H}),
        warmup_bars=20,
        symbols=("BNBUSDT", "BTCUSDT"),
    )

    def on_init(self, ctx: Any) -> None:
        ctx.state.setdefault("last_price", None)

    def on_bar(self, ctx: Any, bar: Bar) -> list[Signal]:
        pos = ctx.position(bar.symbol)
        close = float(bar.close)
        spread = float(self.p.get("spread", 0.005))
        last = ctx.state.get("last_price")
        signals: list[Signal] = []

        if pos is None:
            ctx.state["last_price"] = close
            signals.append(Signal(
                type=SignalType.OPEN_LONG,
                symbol=bar.symbol,
                cash_pct=self.p.get("cash_pct", 0.1),
                reason="建立初始网格底仓",
                tag="grid_init",
            ))
            return signals

        if last is not None:
            if close <= last * (1.0 - spread):
                ctx.state["last_price"] = close
                signals.append(Signal(
                    type=SignalType.ADD_LONG,
                    symbol=bar.symbol,
                    cash_pct=self.p.get("cash_pct", 0.1),
                    reason="网格下跌加仓",
                    tag="grid_buy",
                ))
            elif close >= last * (1.0 + spread):
                ctx.state["last_price"] = close
                signals.append(Signal(
                    type=SignalType.REDUCE_LONG,
                    symbol=bar.symbol,
                    position_pct=0.5,
                    reason="网格上涨止盈",
                    tag="grid_sell",
                ))

        return signals


def autodiscover(package: str = "app.strategies.library") -> list[str]:
    """Import every module in the strategy library package, causing their
    ``@register_strategy`` decorators to fire. Returns imported module names."""
    imported: list[str] = []
    try:
        pkg = importlib.import_module(package)
        for info in pkgutil.iter_modules(pkg.__path__):
            if info.name.startswith("_"):
                continue
            importlib.import_module(f"{package}.{info.name}")
            imported.append(info.name)
    except Exception:
        pass
    return imported
