"""Performance analytics service.

Aggregates fills / positions / MTM mark logs into a unified PnL report:

- summary metrics: total / realized / unrealized PnL, win rate, profit factor,
  annualised Sharpe, max drawdown, best/worst day, daily volatility
- daily PnL series (mark-to-market basis) + cumulative curve
- per-symbol breakdown (PnL, quantity, entry/current price, fills, notional)
- per-day fill activity (count, buy/sell notional)

Pure computation over in-memory store state — no extra infrastructure needed,
suitable for the 1C/896MB production box.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def _val(obj: Any, key: str, default: Any = None) -> Any:
    """Read a field from either a dict or an attribute-style object."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if value is None:
        return None
    try:
        text = str(value).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except ValueError:
        return None


class PerformanceAnalyticsService:
    """Computes the trading performance report from store data."""

    def __init__(self, store: Any):
        self._store = store

    # ── public API ───────────────────────────────────────────────────

    def get_performance_report(self, days: int = 90) -> dict[str, Any]:
        fills = list(getattr(self._store, "fills", {}).values())
        positions = list(getattr(self._store, "positions", {}).values())
        mtm_logs = list(getattr(self._store, "mtm_logs", []))

        symbol_rows = self._symbol_breakdown(fills, positions)
        daily_series, notes = self._daily_series(mtm_logs, fills, days)
        summary = self._summary(fills, positions, daily_series)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "daily_series": daily_series,
            "symbols": symbol_rows,
            "notes": notes,
        }

    # ── internals ────────────────────────────────────────────────────

    def _symbol_breakdown(self, fills: list[Any], positions: list[Any]) -> list[dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}

        def _row(symbol: str) -> dict[str, Any]:
            return rows.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "realized_pnl": 0.0,
                    "unrealized_pnl": 0.0,
                    "total_pnl": 0.0,
                    "quantity": 0.0,
                    "entry_price": 0.0,
                    "current_price": 0.0,
                    "fills": 0,
                    "notional": 0.0,
                },
            )

        for pos in positions:
            symbol = str(_val(pos, "symbol", "?"))
            row = _row(symbol)
            row["realized_pnl"] += _num(_val(pos, "realized_pnl"))
            row["unrealized_pnl"] += _num(_val(pos, "unrealized_pnl"))
            row["quantity"] += _num(_val(pos, "quantity"))
            row["entry_price"] = _num(_val(pos, "entry_price"))
            row["current_price"] = _num(_val(pos, "current_price"))

        for fill in fills:
            symbol = str(_val(fill, "symbol", "?"))
            row = _row(symbol)
            row["fills"] += 1
            row["notional"] += _num(_val(fill, "fill_price")) * _num(_val(fill, "fill_quantity"))

        for row in rows.values():
            row["total_pnl"] = row["realized_pnl"] + row["unrealized_pnl"]

        return sorted(rows.values(), key=lambda r: r["total_pnl"], reverse=True)

    def _daily_series(
        self, mtm_logs: list[Any], fills: list[Any], days: int
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        notes: dict[str, Any] = {
            "pnl_basis": "mark-to-market",
            "mtm_points": len(mtm_logs),
            "fills": len(fills),
        }

        # 1) daily portfolio unrealized snapshot: last value per position per day
        entries: list[tuple[datetime, Any]] = []
        for log in mtm_logs:
            ts = _to_datetime(_val(log, "created_at"))
            if ts is not None:
                entries.append((ts, log))
        entries.sort(key=lambda item: item[0])

        snapshots: dict[str, dict[str, float]] = {}
        for ts, log in entries:
            day = ts.astimezone(timezone.utc).date().isoformat()
            position_id = str(_val(log, "position_id", _val(log, "symbol", "?")))
            snapshots.setdefault(day, {})[position_id] = _num(_val(log, "unrealized_pnl"))

        daily_unrealized = {day: sum(per_position.values()) for day, per_position in snapshots.items()}

        # 2) daily fill activity
        activity: dict[str, dict[str, Any]] = {}
        for fill in fills:
            ts = _to_datetime(_val(fill, "created_at"))
            if ts is None:
                continue
            day = ts.astimezone(timezone.utc).date().isoformat()
            entry = activity.setdefault(day, {"fills": 0, "buy_notional": 0.0, "sell_notional": 0.0})
            entry["fills"] += 1
            notional = _num(_val(fill, "fill_price")) * _num(_val(fill, "fill_quantity"))
            side = str(_val(fill, "side", "")).upper()
            if side.startswith("BUY") or side in ("LONG", "OPEN_LONG"):
                entry["buy_notional"] += notional
            else:
                entry["sell_notional"] += notional

        # 3) merge into unified day list, cap to window
        all_days = sorted(set(daily_unrealized) | set(activity))
        if days > 0:
            all_days = all_days[-days:]

        series: list[dict[str, Any]] = []
        prev_unrealized = 0.0
        cumulative = 0.0
        for day in all_days:
            unrealized = daily_unrealized.get(day, prev_unrealized)
            pnl = unrealized - prev_unrealized
            cumulative += pnl
            act = activity.get(day, {"fills": 0, "buy_notional": 0.0, "sell_notional": 0.0})
            series.append(
                {
                    "date": day,
                    "pnl": round(pnl, 2),
                    "cumulative": round(cumulative, 2),
                    "unrealized": round(unrealized, 2),
                    "fills": act["fills"],
                    "buy_notional": round(act["buy_notional"], 2),
                    "sell_notional": round(act["sell_notional"], 2),
                }
            )
            prev_unrealized = unrealized

        notes["days"] = len(series)
        return series, notes

    def _summary(
        self, fills: list[Any], positions: list[Any], daily_series: list[dict[str, Any]]
    ) -> dict[str, Any]:
        realized = sum(_num(_val(p, "realized_pnl")) for p in positions)
        unrealized = sum(_num(_val(p, "unrealized_pnl")) for p in positions)

        pnls = [row["pnl"] for row in daily_series]
        positive = [p for p in pnls if p > 0]
        negative = [p for p in pnls if p < 0]

        win_rate = (len(positive) / len(pnls)) if pnls else 0.0
        gross_profit = sum(positive)
        gross_loss = abs(sum(negative))
        if gross_loss > 0:
            profit_factor: float | None = gross_profit / gross_loss
        else:
            profit_factor = None if gross_profit <= 0 else None
            # all-positive or empty: report None (infinite) to keep JSON valid

        mean = sum(pnls) / len(pnls) if pnls else 0.0
        variance = sum((p - mean) ** 2 for p in pnls) / len(pnls) if len(pnls) > 1 else 0.0
        std = math.sqrt(variance)
        sharpe = (mean / std) * math.sqrt(365.0) if std > 0 else 0.0

        max_drawdown = 0.0
        peak = float("-inf")
        for row in daily_series:
            cum = row["cumulative"]
            if cum > peak:
                peak = cum
            drawdown = peak - cum
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return {
            "total_pnl": round(realized + unrealized, 2),
            "realized_pnl": round(realized, 2),
            "unrealized_pnl": round(unrealized, 2),
            "total_fills": len(fills),
            "open_positions": sum(1 for p in positions if abs(_num(_val(p, "quantity"))) > 1e-12),
            "days_reported": len(daily_series),
            "win_rate": round(win_rate, 4),
            "profit_factor": round(profit_factor, 4) if profit_factor is not None else None,
            "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_drawdown, 2),
            "best_day": round(max(pnls), 2) if pnls else 0.0,
            "worst_day": round(min(pnls), 2) if pnls else 0.0,
            "avg_daily_pnl": round(mean, 2),
            "volatility_daily": round(std, 2),
            "positive_days": len(positive),
            "negative_days": len(negative),
        }
