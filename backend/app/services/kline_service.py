"""Historical & realtime kline (OHLCV) data service.

Feeds the pluggable strategy framework with real market data.

Data flow:
    Binance public REST /klines  →  in-memory ring buffer
                                 →  optional Postgres persistence
                                 →  strategy framework kline_provider

No API key required — uses only public market-data endpoints.
Designed to work in three modes:
- memory-only (default dev): fast, loses history on restart
- postgres (production): durable, survives restarts
- hybrid: memory hot cache + PG warm storage (automatic when PG enabled)
"""

import json
import threading
import time
import urllib.request
import urllib.error
from collections import defaultdict
from decimal import Decimal
from typing import Any, Callable

from app.core.logging import get_logger
from app.strategies.signal import Bar

logger = get_logger(__name__)

# period string → Binance interval + milliseconds
_PERIOD_MAP: dict[str, tuple[str, int]] = {
    "1m": ("1m", 60_000),
    "5m": ("5m", 300_000),
    "15m": ("15m", 900_000),
    "1h": ("1h", 3_600_000),
    "4h": ("4h", 14_400_000),
    "1d": ("1d", 86_400_000),
}

_BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
_MAX_BARS_IN_MEMORY = 1500   # ring buffer cap per (symbol, period)


class KlineService:
    """Fetches, caches and serves historical klines for the strategy framework."""

    def __init__(
        self,
        persist_hook: Callable[[str, str, list[Bar]], None] | None = None,
        load_hook: Callable[[str, str, int], list[Bar]] | None = None,
        base_url: str = _BINANCE_KLINES_URL,
        timeout: float = 10.0,
    ):
        # (symbol, period) → list[Bar], oldest first, capped at _MAX_BARS_IN_MEMORY
        self._buffers: dict[tuple[str, str], list[Bar]] = defaultdict(list)
        self._lock = threading.RLock()
        self._persist_hook = persist_hook      # optional PG write
        self._load_hook = load_hook            # optional PG read
        self._base_url = base_url
        self._timeout = timeout
        self.last_fetch_at: dict[tuple[str, str], float] = {}
        self.fetch_errors: dict[tuple[str, str], str] = {}
        self._fetching: set[tuple[str, str]] = set()

    # ── public read API (used by strategy framework) ──────────────────

    def get_klines(self, symbol: str, period: str, count: int = 200) -> list[Bar]:
        """Return up to ``count`` most recent bars, oldest first.

        Serves from the in-memory buffer; if insufficient, attempts a
        backfill from PG (when configured) then from the exchange.
        """
        key = (symbol.upper(), period)
        with self._lock:
            bars = list(self._buffers.get(key, []))

        with self._lock:
            busy = key in self._fetching
        if len(bars) < count and not busy:
            # try warm storage first (cheap), then exchange (network)
            bars = self._backfill_from_store(symbol, period, count, existing=bars)
        if len(bars) < count and not busy:
            with self._lock:
                self._fetching.add(key)
            try:
                fetched = self.fetch_history(symbol, period, limit=min(count, 1000))
            finally:
                with self._lock:
                    self._fetching.discard(key)
            if fetched:
                bars = fetched

        return bars[-count:] if len(bars) > count else bars

    def latest_bar(self, symbol: str, period: str) -> Bar | None:
        bars = self.get_klines(symbol, period, 1)
        return bars[-1] if bars else None

    def has_enough_data(self, symbol: str, period: str, count: int) -> bool:
        key = (symbol.upper(), period)
        with self._lock:
            return len(self._buffers.get(key, [])) >= count

    # ── fetching / ingestion ──────────────────────────────────────────

    def fetch_history(self, symbol: str, period: str, limit: int = 500) -> list[Bar]:
        """Fetch historical klines from Binance public API and ingest them."""
        symbol = symbol.upper()
        interval, _ = self._resolve_period(period)
        url = f"{self._base_url}?symbol={symbol}&interval={interval}&limit={min(limit, 1000)}"
        try:
            raw = self._http_get_json(url)
            bars = [Bar.from_list(symbol, row) for row in raw]
            self.ingest(symbol, period, bars)
            key = (symbol, period)
            self.last_fetch_at[key] = time.time()
            self.fetch_errors.pop(key, None)
            logger.info("kline_fetch_ok", symbol=symbol, period=period, count=len(bars))
            return self.get_klines(symbol, period, limit)
        except Exception as exc:  # noqa: BLE001
            key = (symbol, period)
            self.fetch_errors[key] = str(exc)[:300]
            logger.warning("kline_fetch_error", symbol=symbol, period=period, error=str(exc)[:200])
            return self.get_klines(symbol, period, limit)

    def ingest(self, symbol: str, period: str, bars: list[Bar]) -> int:
        """Merge new bars into the buffer, dedup by open_time. Returns new count."""
        if not bars:
            return 0
        symbol = symbol.upper()
        key = (symbol, period)
        with self._lock:
            existing = self._buffers[key]
            known = {b.open_time for b in existing}
            new_bars = [b for b in bars if b.open_time not in known]
            if new_bars:
                merged = existing + new_bars
                merged.sort(key=lambda b: b.open_time)
                if len(merged) > _MAX_BARS_IN_MEMORY:
                    merged = merged[-_MAX_BARS_IN_MEMORY:]
                self._buffers[key] = merged
        if new_bars and self._persist_hook is not None:
            try:
                self._persist_hook(symbol, period, new_bars)
            except Exception as exc:  # noqa: BLE001
                logger.warning("kline_persist_error", symbol=symbol, error=str(exc)[:200])
        return len(new_bars)

    def refresh_symbols(self, symbols: list[str], period: str = "1h", limit: int = 200) -> dict[str, int]:
        """Refresh the latest bars for a set of symbols (called by scheduler)."""
        result: dict[str, int] = {}
        for symbol in symbols:
            before = len(self.get_klines(symbol, period, 1))
            self.fetch_history(symbol, period, limit=limit)
            after = len(self.get_klines(symbol, period, 1))
            result[symbol] = max(0, after - before)
        return result

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "buffered_series": len(self._buffers),
                "series": [
                    {"symbol": s, "period": p, "bars": len(bars)}
                    for (s, p), bars in self._buffers.items()
                ],
                "fetch_errors": {f"{s}/{p}": e for (s, p), e in self.fetch_errors.items()},
            }

    # ── internals ─────────────────────────────────────────────────────

    def _backfill_from_store(self, symbol: str, period: str, count: int, existing: list[Bar]) -> list[Bar]:
        if self._load_hook is None:
            return existing
        try:
            stored = self._load_hook(symbol.upper(), period, count)
            if not stored:
                return existing
            known = {b.open_time for b in existing}
            merged = [b for b in stored if b.open_time not in known] + existing
            merged.sort(key=lambda b: b.open_time)
            with self._lock:
                self._buffers[(symbol.upper(), period)] = merged[-_MAX_BARS_IN_MEMORY:]
            return merged
        except Exception as exc:  # noqa: BLE001
            logger.warning("kline_load_error", symbol=symbol, error=str(exc)[:200])
            return existing

    def _resolve_period(self, period: str) -> tuple[str, int]:
        if period not in _PERIOD_MAP:
            raise ValueError(f"unsupported period '{period}', supported: {list(_PERIOD_MAP)}")
        return _PERIOD_MAP[period]

    def _http_get_json(self, url: str) -> Any:
        req = urllib.request.Request(url, headers={"User-Agent": "quant-kline-service/1.0"})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
