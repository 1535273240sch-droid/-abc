"""Strategy runtime context: the strategy's eyes and memory.

Everything a strategy needs flows through this object — market data,
indicators, positions, account state, private persistent state, and time.

The same context interface is served by three different backends:
- backtest: historical bars, simulated clock, simulated fills
- paper:    live tickers + local kline store, real clock, paper fills
- live:     live tickers, real clock, real exchange fills

Strategies therefore never know (or care) which mode they run in.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from app.strategies.signal import Bar


class StrategyContext:
    """Runtime context handed to a strategy on every callback.

    Data providers are injected as callables so the context stays
    storage-agnostic (in-memory store, Postgres, or backtest feed).
    """

    def __init__(
        self,
        strategy_id: str,
        kline_provider: Callable[[str, str, int], list[Bar]] | None = None,
        ticker_provider: Callable[[str], Any] | None = None,
        indicator_provider: Callable[[str, list[Bar], dict], list[float | None]] | None = None,
        position_provider: Callable[[str], Any] | None = None,
        cash_provider: Callable[[], Decimal] | None = None,
        portfolio_provider: Callable[[], Decimal] | None = None,
        state_store: dict[str, Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self.strategy_id = strategy_id
        self._kline_provider = kline_provider
        self._ticker_provider = ticker_provider
        self._indicator_provider = indicator_provider
        self._position_provider = position_provider
        self._cash_provider = cash_provider
        self._portfolio_provider = portfolio_provider
        self._state = state_store if state_store is not None else {}
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._bar_cache: dict[tuple[str, str, int], list[Bar]] = {}

    # ── time ──────────────────────────────────────────────────────────

    def now(self) -> datetime:
        """Current time. In backtests this is historical bar time."""
        return self._clock()

    # ── market data ───────────────────────────────────────────────────

    def klines(self, symbol: str, period: str = "1h", count: int = 200) -> list[Bar]:
        """Historical klines, oldest first. Cached per (symbol, period, count)."""
        key = (symbol, period, count)
        if key not in self._bar_cache:
            if self._kline_provider is None:
                raise RuntimeError("no kline provider configured for this context")
            self._bar_cache[key] = self._kline_provider(symbol, period, count)
        return self._bar_cache[key]

    def ticker(self, symbol: str) -> Any:
        if self._ticker_provider is None:
            raise RuntimeError("no ticker provider configured for this context")
        return self._ticker_provider(symbol)

    # ── indicators ────────────────────────────────────────────────────

    def indicator(
        self,
        name: str,
        symbol: str,
        period: str = "1h",
        count: int = 200,
        **params: Any,
    ) -> float | None:
        """Latest value of an indicator, e.g. ctx.indicator('sma', 'BTCUSDT', length=20).

        Returns None when there is insufficient history (warmup not complete).
        """
        series = self.indicator_series(name, symbol, period, count, **params)
        return series[-1] if series else None

    def indicator_series(
        self,
        name: str,
        symbol: str,
        period: str = "1h",
        count: int = 200,
        **params: Any,
    ) -> list[float | None]:
        if self._indicator_provider is None:
            raise RuntimeError("no indicator provider configured for this context")
        bars = self.klines(symbol, period, count)
        return self._indicator_provider(name, bars, params)

    # ── account & positions ───────────────────────────────────────────

    def position(self, symbol: str) -> Any:
        """Current position for symbol, or None when flat."""
        if self._position_provider is None:
            return None
        return self._position_provider(symbol)

    def available_cash(self) -> Decimal:
        if self._cash_provider is None:
            return Decimal("0")
        return self._cash_provider()

    def portfolio_value(self) -> Decimal:
        if self._portfolio_provider is None:
            return Decimal("0")
        return self._portfolio_provider()

    # ── strategy private state ────────────────────────────────────────

    @property
    def state(self) -> dict[str, Any]:
        """Persistent per-strategy KV store. Survives restarts when the
        underlying dict is backed by the store's persisted fields.

        Typical uses: entry price, grid level index, last signal time,
        trailing-stop anchor, cooldown counters.
        """
        return self._state

    def clear_cache(self) -> None:
        """Drop cached bar series (call between bars in streaming mode)."""
        self._bar_cache.clear()
