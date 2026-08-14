"""Technical indicator engine with per-series memoization.

Pure-Python implementations (no native deps) of the most common
indicators. Each function takes a list of Bars and returns a list of
``float | None`` aligned with the input (leading None during warmup).

The registry caches results keyed by (name, bar-count, last-bar-time,
params) so repeated lookups within one bar tick are free.
"""

from decimal import Decimal
from typing import Any, Callable

from app.strategies.signal import Bar

IndicatorFunc = Callable[..., list[float | None]]


def _closes(bars: list[Bar]) -> list[float]:
    return [float(b.close) for b in bars]


# ── indicator implementations ─────────────────────────────────────────

def sma(bars: list[Bar], length: int = 20, **_: Any) -> list[float | None]:
    closes = _closes(bars)
    out: list[float | None] = [None] * len(closes)
    if length <= 0 or len(closes) < length:
        return out
    window_sum = sum(closes[:length])
    out[length - 1] = window_sum / length
    for i in range(length, len(closes)):
        window_sum += closes[i] - closes[i - length]
        out[i] = window_sum / length
    return out


def ema(bars: list[Bar], length: int = 20, **_: Any) -> list[float | None]:
    closes = _closes(bars)
    out: list[float | None] = [None] * len(closes)
    if length <= 0 or len(closes) < length:
        return out
    k = 2 / (length + 1)
    seed = sum(closes[:length]) / length
    out[length - 1] = seed
    prev = seed
    for i in range(length, len(closes)):
        prev = closes[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def macd(
    bars: list[Bar],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    **_: Any,
) -> list[float | None]:
    """Returns the MACD histogram (macd_line - signal_line)."""
    closes = _closes(bars)
    out: list[float | None] = [None] * len(closes)
    if len(closes) < slow + signal:
        return out

    def _ema_series(data: list[float], length: int) -> list[float | None]:
        res: list[float | None] = [None] * len(data)
        if len(data) < length:
            return res
        k = 2 / (length + 1)
        prev = sum(data[:length]) / length
        res[length - 1] = prev
        for i in range(length, len(data)):
            prev = data[i] * k + prev * (1 - k)
            res[i] = prev
        return res

    fast_e = _ema_series(closes, fast)
    slow_e = _ema_series(closes, slow)
    macd_line: list[float | None] = [None] * len(closes)
    for i in range(len(closes)):
        if fast_e[i] is not None and slow_e[i] is not None:
            macd_line[i] = fast_e[i] - slow_e[i]  # type: ignore[operator]

    valid = [(i, v) for i, v in enumerate(macd_line) if v is not None]
    if len(valid) < signal:
        return out
    sig_vals = [v for _, v in valid]
    sig_series = _ema_series(sig_vals, signal)
    for j, (idx, _) in enumerate(valid):
        if sig_series[j] is not None:
            out[idx] = macd_line[idx] - sig_series[j]  # type: ignore[operator]
    return out


def rsi(bars: list[Bar], length: int = 14, **_: Any) -> list[float | None]:
    closes = _closes(bars)
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= length:
        return out
    gains, losses = [], []
    for i in range(1, length + 1):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / length
    avg_loss = sum(losses) / length
    out[length] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(length + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (length - 1) + max(delta, 0.0)) / length
        avg_loss = (avg_loss * (length - 1) + max(-delta, 0.0)) / length
        out[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def bollinger(
    bars: list[Bar],
    length: int = 20,
    mult: float = 2.0,
    band: str = "mid",
    **_: Any,
) -> list[float | None]:
    """band: 'upper' | 'mid' | 'lower' | 'pctb' (percent-b position)."""
    closes = _closes(bars)
    out: list[float | None] = [None] * len(closes)
    if len(closes) < length:
        return out
    for i in range(length - 1, len(closes)):
        window = closes[i - length + 1 : i + 1]
        mean = sum(window) / length
        var = sum((c - mean) ** 2 for c in window) / length
        std = var ** 0.5
        upper, lower = mean + mult * std, mean - mult * std
        if band == "upper":
            out[i] = upper
        elif band == "lower":
            out[i] = lower
        elif band == "pctb":
            out[i] = (closes[i] - lower) / (upper - lower) if upper != lower else 0.5
        else:
            out[i] = mean
    return out


def atr(bars: list[Bar], length: int = 14, **_: Any) -> list[float | None]:
    out: list[float | None] = [None] * len(bars)
    if len(bars) <= length:
        return out
    trs: list[float] = []
    for i in range(1, len(bars)):
        h, l, pc = float(bars[i].high), float(bars[i].low), float(bars[i - 1].close)
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    prev = sum(trs[:length]) / length
    out[length] = prev
    for i in range(length, len(trs)):
        prev = (prev * (length - 1) + trs[i]) / length
        out[i + 1] = prev
    return out


def highest(bars: list[Bar], length: int = 20, **_: Any) -> list[float | None]:
    out: list[float | None] = [None] * len(bars)
    for i in range(length - 1, len(bars)):
        out[i] = max(float(b.high) for b in bars[i - length + 1 : i + 1])
    return out


def lowest(bars: list[Bar], length: int = 20, **_: Any) -> list[float | None]:
    out: list[float | None] = [None] * len(bars)
    for i in range(length - 1, len(bars)):
        out[i] = min(float(b.low) for b in bars[i - length + 1 : i + 1])
    return out


# ── registry ──────────────────────────────────────────────────────────

class IndicatorRegistry:
    """Name → indicator function, with memoization per bar series."""

    def __init__(self) -> None:
        self._funcs: dict[str, IndicatorFunc] = {}
        self._cache: dict[tuple, list[float | None]] = {}

    def register(self, name: str, func: IndicatorFunc) -> None:
        self._funcs[name.lower()] = func

    def available(self) -> list[str]:
        return sorted(self._funcs)

    def compute(self, name: str, bars: list[Bar], params: dict[str, Any]) -> list[float | None]:
        func = self._funcs.get(name.lower())
        if func is None:
            raise KeyError(f"unknown indicator '{name}', available: {self.available()}")
        key = (
            name.lower(),
            len(bars),
            bars[-1].open_time if bars else 0,
            tuple(sorted((k, str(v)) for k, v in params.items())),
        )
        if key not in self._cache:
            self._cache[key] = func(bars, **params)
        return self._cache[key]

    def clear_cache(self) -> None:
        self._cache.clear()


def default_indicator_registry() -> IndicatorRegistry:
    reg = IndicatorRegistry()
    reg.register("sma", sma)
    reg.register("ema", ema)
    reg.register("macd", macd)
    reg.register("rsi", rsi)
    reg.register("bollinger", bollinger)
    reg.register("atr", atr)
    reg.register("highest", highest)
    reg.register("lowest", lowest)
    return reg
