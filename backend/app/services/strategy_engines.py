"""Pluggable strategy signal-generation engines.

Each engine encapsulates the signal logic for a strategy *kind* (trend,
arbitrage, grid, …).  Engines are registered in a registry and looked up
at runtime, replacing the former hard-coded ``_signals_for`` switch in
``StrategyRuntimeService``.

New strategy kinds can be added by:

1. Implementing :class:`StrategyEngine`.
2. Registering it via ``registry.register("my_kind", MyEngine())``.

The runtime service never needs to change.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any


class StrategyEngine(ABC):
    """Abstract signal-generation engine.

    ``generate_signals`` must return a list of signal dicts.  Each signal
    dict has at minimum:

    - ``symbol`` (str)
    - ``action`` (``"buy"`` | ``"sell"`` | ``"hold"``)
    - ``status`` (``"pending"`` | ``"blocked"`` | ``"no_signal"``)
    - ``reason`` (str, optional – when blocked / no_signal)
    - ``quantity`` (str, optional – required when action is ``"buy"``)
    - ``signal`` (str, optional – human-readable signal name)
    """

    @abstractmethod
    def generate_signals(
        self,
        strategy: Any,
        quality: dict[str, Any],
        tickers: dict[str, Any],
    ) -> list[dict[str, Any]]:
        ...

    # -- helpers shared by all engines ----------------------------------

    @staticmethod
    def _symbol_for_kind(kind: str) -> str:
        return {
            "trend": "BTCUSDT",
            "arbitrage": "ETHUSDT",
            "grid": "BNBUSDT",
        }.get(kind or "", "BTCUSDT")

    @staticmethod
    def _market_blocked(symbol: str, quality: dict[str, Any]) -> dict | None:
        """Return a blocked signal dict if market quality prevents trading."""
        if any(
            issue.get("code") == "PUBLIC_FEED_UNAVAILABLE"
            for issue in quality.get("issues", [])
        ):
            return {
                "symbol": symbol,
                "action": "hold",
                "status": "blocked",
                "reason": "public_feed_unavailable",
                "data_quality": quality["status"],
            }
        return None


class TrendFollowingEngine(StrategyEngine):
    """Simple trend-following: buy when 24h change is positive."""

    def generate_signals(self, strategy, quality, tickers):
        symbol = self._symbol_for_kind(strategy.kind)
        ticker = tickers.get(symbol)
        if not ticker:
            return [{"symbol": symbol, "action": "hold", "status": "blocked", "reason": "ticker_missing"}]
        blocked = self._market_blocked(symbol, quality)
        if blocked:
            return [blocked]
        change = Decimal(str(getattr(ticker, "change_24h", "0")).replace("+", ""))
        if change > 0:
            quantity = str(strategy.parameters.get("paper_quantity", "0.01000000"))
            return [{
                "symbol": symbol,
                "action": "buy",
                "quantity": quantity,
                "signal": "positive_24h_trend",
                "status": "pending",
            }]
        return [{
            "symbol": symbol,
            "action": "hold",
            "status": "no_signal",
            "reason": "signal_conditions_not_met",
            "data_quality": quality["status"],
        }]


class ArbitrageEngine(StrategyEngine):
    """Cross-exchange arbitrage placeholder.

    In paper mode there is only one exchange, so the engine always
    reports ``no_signal`` with the appropriate reason.
    """

    def generate_signals(self, strategy, quality, tickers):
        symbol = self._symbol_for_kind(strategy.kind)
        ticker = tickers.get(symbol)
        if not ticker:
            return [{"symbol": symbol, "action": "hold", "status": "blocked", "reason": "ticker_missing"}]
        blocked = self._market_blocked(symbol, quality)
        if blocked:
            return [blocked]
        return [{
            "symbol": symbol,
            "action": "hold",
            "status": "no_signal",
            "reason": "cross_exchange_spread_unavailable",
            "data_quality": quality["status"],
        }]


class GridTradingEngine(StrategyEngine):
    """Grid trading: generate buy signals at grid intervals.

    The paper implementation produces a single buy signal when the price
    is below the grid midpoint, simulating a grid level trigger.
    """

    def generate_signals(self, strategy, quality, tickers):
        symbol = self._symbol_for_kind(strategy.kind)
        ticker = tickers.get(symbol)
        if not ticker:
            return [{"symbol": symbol, "action": "hold", "status": "blocked", "reason": "ticker_missing"}]
        blocked = self._market_blocked(symbol, quality)
        if blocked:
            return [blocked]
        levels = int(strategy.parameters.get("grid_levels", 10))
        spread = Decimal(str(strategy.parameters.get("spread", "0.005")))
        last = Decimal(str(getattr(ticker, "last_price", "0")))
        high = Decimal(str(getattr(ticker, "high_24h", "0")))
        low = Decimal(str(getattr(ticker, "low_24h", "0")))
        if high <= low or last <= 0:
            return [{
                "symbol": symbol,
                "action": "hold",
                "status": "no_signal",
                "reason": "invalid_price_range",
                "data_quality": quality["status"],
            }]
        midpoint = (high + low) / Decimal("2")
        level_step = (high - low) * spread / Decimal(str(levels))
        # Buy when price is below midpoint - one step (a grid level)
        if last < midpoint - level_step:
            quantity = str(strategy.parameters.get("paper_quantity", "0.01000000"))
            return [{
                "symbol": symbol,
                "action": "buy",
                "quantity": quantity,
                "signal": "grid_level_buy",
                "status": "pending",
            }]
        return [{
            "symbol": symbol,
            "action": "hold",
            "status": "no_signal",
            "reason": "price_above_grid_level",
            "data_quality": quality["status"],
        }]


class DefaultEngine(StrategyEngine):
    """Fallback engine used when no engine is registered for a kind."""

    def generate_signals(self, strategy, quality, tickers):
        symbol = self._symbol_for_kind(strategy.kind)
        ticker = tickers.get(symbol)
        if not ticker:
            return [{"symbol": symbol, "action": "hold", "status": "blocked", "reason": "ticker_missing"}]
        blocked = self._market_blocked(symbol, quality)
        if blocked:
            return [blocked]
        return [{
            "symbol": symbol,
            "action": "hold",
            "status": "no_signal",
            "reason": "signal_conditions_not_met",
            "data_quality": quality["status"],
        }]


class StrategyEngineRegistry:
    """Registry mapping strategy *kind* → :class:`StrategyEngine`."""

    def __init__(self):
        self._engines: dict[str, StrategyEngine] = {}
        self._default = DefaultEngine()

    def register(self, kind: str, engine: StrategyEngine) -> None:
        self._engines[kind] = engine

    def get(self, kind: str | None) -> StrategyEngine:
        if kind and kind in self._engines:
            return self._engines[kind]
        return self._default

    @property
    def registered_kinds(self) -> list[str]:
        return sorted(self._engines.keys())


def default_registry() -> StrategyEngineRegistry:
    """Pre-registered registry with built-in engines."""
    reg = StrategyEngineRegistry()
    reg.register("trend", TrendFollowingEngine())
    reg.register("arbitrage", ArbitrageEngine())
    reg.register("grid", GridTradingEngine())
    return reg
