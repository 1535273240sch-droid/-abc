"""Historical kline data import and management.

Feeds the backtest engine with durable OHLCV data. Supports:

1. Binance public REST — paginated download (max 1000 per request)
2. CSV upload — headerless ``timestamp,open,high,low,close,volume``

Persistence hooks into the ``HistoricalKlineModel`` table when PostgreSQL
is available, otherwise keeps data in the KlineService in-memory buffer.
"""

import csv
import io
import json
import logging
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.strategies.signal import Bar

logger = get_logger(__name__)

_BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
_MAX_FETCH_LIMIT = 1000
_PERIOD_MS: dict[str, int] = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000,
    "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
}


class HistoricalDataService:
    """Import, persist and serve historical OHLCV for backtesting."""

    def __init__(self, kline_service: Any = None):
        self._kline_service = kline_service
        self._persist_fn: Any | None = None

    def connect_persistence(self, persist_fn: Any, load_fn: Any | None = None) -> None:
        """Wire PG persist/load hooks. ``persist_fn(symbol, period, bars)``, ``load_fn(symbol, period, limit)``."""
        self._persist_fn = persist_fn
        if load_fn is not None and self._kline_service is not None:
            self._kline_service._load_hook = load_fn

    # ── Binance paginated import ──────────────────────────────────────

    def import_binance(
        self,
        symbol: str,
        period: str,
        start_ms: int,
        end_ms: int,
        on_progress: Any | None = None,
    ) -> dict:
        """Download klines from Binance in 1000-bar pages. Returns stats."""
        symbol = symbol.upper()
        if period not in _PERIOD_MS:
            raise ValueError(f"unsupported period '{period}', supported: {list(_PERIOD_MS)}")

        all_bars: list[Bar] = []
        cursor = start_ms
        total_pages = 0
        errors = 0

        while cursor < end_ms:
            params = urllib.parse.urlencode({
                "symbol": symbol, "interval": period,
                "startTime": cursor, "endTime": end_ms, "limit": _MAX_FETCH_LIMIT,
            })
            url = f"{_BINANCE_KLINES_URL}?{params}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "quant-historical-import/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    rows = json.loads(resp.read().decode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                errors += 1
                logger.warning("historical_binance_page_error", symbol=symbol, error=str(exc)[:200])
                if errors >= 5:
                    break
                time.sleep(1)
                continue

            if not rows:
                break

            bars = [Bar.from_list(symbol, row) for row in rows]
            all_bars.extend(bars)
            total_pages += 1
            cursor = rows[-1][6] + 1

            if on_progress is not None:
                on_progress(total_pages, len(all_bars))

            if len(rows) < _MAX_FETCH_LIMIT:
                break
            time.sleep(0.2)

        if all_bars:
            if self._persist_fn:
                try:
                    self._persist_fn(symbol, period, all_bars)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("historical_persist_error", symbol=symbol, error=str(exc)[:200])
            if self._kline_service:
                self._kline_service.ingest(symbol, period, all_bars)

        return {
            "symbol": symbol,
            "period": period,
            "bars_imported": len(all_bars),
            "pages_fetched": total_pages,
            "errors": errors,
            "time_range": f"{all_bars[0].open_time}-{all_bars[-1].close_time}" if all_bars else "empty",
        }

    # ── CSV import ───────────────────────────────────────────────────

    def import_csv(
        self,
        symbol: str,
        period: str,
        csv_text: str,
        delimiter: str = ",",
    ) -> dict:
        """Parse CSV text into Bar objects. Returns stats.

        Expected columns: ``open_time,open,high,low,close,volume``
        open_time is either a unix-ms integer or ISO datetime string.
        """
        symbol = symbol.upper()
        bars: list[Bar] = []
        errors = 0
        reader = csv.reader(io.StringIO(csv_text), delimiter=delimiter)

        for i, row in enumerate(reader):
            if i == 0 and row[0].strip().lower()[:10] in ("open_time", "timestamp", "date", "time"):
                continue
            try:
                if len(row) < 6:
                    errors += 1
                    continue
                open_time = _parse_time(row[0])
                bars.append(Bar(
                    symbol=symbol,
                    open_time=open_time,
                    open=Decimal(row[1]),
                    high=Decimal(row[2]),
                    low=Decimal(row[3]),
                    close=Decimal(row[4]),
                    volume=Decimal(row[5]),
                    close_time=open_time + _PERIOD_MS.get(period, 86_400_000) - 1,
                ))
            except Exception:  # noqa: BLE001
                errors += 1

        bars.sort(key=lambda b: b.open_time)

        if bars:
            if self._persist_fn:
                try:
                    self._persist_fn(symbol, period, bars)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("historical_csv_persist_error", symbol=symbol, error=str(exc)[:200])
            if self._kline_service:
                self._kline_service.ingest(symbol, period, bars)

        return {
            "symbol": symbol,
            "period": period,
            "bars_imported": len(bars),
            "errors": errors,
            "time_range": f"{bars[0].open_time}-{bars[-1].close_time}" if bars else "empty",
        }

    # ── query ───────────────────────────────────────────────────────

    def get_bars(self, symbol: str, period: str, limit: int = 10000) -> list[Bar]:
        """Retrieve up to ``limit`` historical bars, oldest first."""
        if self._kline_service:
            return self._kline_service.get_klines(symbol, period, limit)
        return []

    def list_series(self) -> list[dict]:
        """Summary of all available historical data series."""
        if self._kline_service:
            return self._kline_service.status().get("series", [])
        return []

    def delete_series(self, symbol: str, period: str) -> dict:
        """Remove a series from the in-memory buffer."""
        if self._kline_service:
            key = (symbol.upper(), period)
            count = len(self._kline_service._buffers.get(key, []))
            self._kline_service._buffers.pop(key, None)
            self._kline_service.last_fetch_at.pop(key, None)
            self._kline_service.fetch_errors.pop(key, None)
            return {"deleted": count, "symbol": symbol.upper(), "period": period}
        return {"deleted": 0}


def _parse_time(value: str) -> int:
    """Parse a unix-ms int or ISO datetime string to unix-ms."""
    value = value.strip()
    try:
        return int(value)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    raise ValueError(f"cannot parse time: {value!r}")
