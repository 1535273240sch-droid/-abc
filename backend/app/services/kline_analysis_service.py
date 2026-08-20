"""AI-powered kline technical analysis service.

On-demand analysis combining precise local indicator computation with the
built-in LLM gateway (stepfun / deepseek):

- locally computed indicators: MA(7/25/99), RSI(14), MACD(12/26/9),
  BOLL(20,2), ATR(14), volume ratio — computed locally so numbers fed to
  the LLM are exact and cheap
- swing-fractal support/resistance detection with touch-count strength
- LLM structured analysis (trend / confidence / summary / detail /
  suggestion + level prices), robust JSON extraction, price sanity
  validation, and a fully local fallback when the model is unreachable

Pure in-memory computation — no extra infrastructure, safe for the
1C/896MB production box.
"""

from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_PERIOD_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

_TREND_LABEL = {"bullish": "看多", "bearish": "看空", "neutral": "震荡"}


# ── indicator math helpers ──────────────────────────────────────────


def _sma(values: list[float], n: int) -> float | None:
    if len(values) < n or n <= 0:
        return None
    return sum(values[-n:]) / n


def _ema_series(values: list[float], n: int) -> list[float]:
    if not values:
        return []
    k = 2.0 / (n + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1.0 - k))
    return out


def _rsi(closes: list[float], n: int = 14) -> float | None:
    if len(closes) < n + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(-n, 0):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    avg_gain, avg_loss = gains / n, losses / n
    if avg_loss <= 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _macd(closes: list[float]) -> tuple[float | None, float | None, float | None]:
    if len(closes) < 35:
        return None, None, None
    ema12 = _ema_series(closes, 12)
    ema26 = _ema_series(closes, 26)
    dif = [a - b for a, b in zip(ema12, ema26)]
    dea = _ema_series(dif, 9)
    return dif[-1], dea[-1], dif[-1] - dea[-1]


def _boll(closes: list[float], n: int = 20, k: float = 2.0) -> tuple[float | None, float | None, float | None]:
    mid = _sma(closes, n)
    if mid is None:
        return None, None, None
    window = closes[-n:]
    variance = sum((c - mid) ** 2 for c in window) / n
    std = math.sqrt(variance)
    return mid + k * std, mid, mid - k * std


def _atr(bars: list[Any], n: int = 14) -> float | None:
    if len(bars) < n + 1:
        return None
    trs: list[float] = []
    for i in range(-n, 0):
        cur, prev = bars[i], bars[i - 1]
        high, low = float(cur.high), float(cur.low)
        prev_close = float(prev.close)
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(trs) / n


class KlineAnalysisService:
    """Kline technical analysis: local indicators + LLM narrative."""

    def __init__(self, store: Any):
        self._store = store

    # ── public API ───────────────────────────────────────────────────

    def analyze(self, symbol: str, period: str = "1h", bars_count: int = 150) -> dict[str, Any]:
        symbol = (symbol or "").strip().upper()
        period = period if period in _PERIOD_MS else "1h"
        bars_count = max(60, min(bars_count, 300))

        bars = self._fresh_bars(symbol, period, bars_count)
        if len(bars) < 30:
            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "period": period,
                "source": "local",
                "error": "INSUFFICIENT_DATA",
                "detail": f"{symbol} {period} K线数据不足（当前 {len(bars)} 根，至少需要 30 根）",
                "indicators": {},
                "levels": {"supports": [], "resistances": []},
                "analysis": {
                    "trend": "neutral",
                    "trend_label": "数据不足",
                    "confidence": 0,
                    "summary": "K线数据不足，无法生成分析。",
                    "detail": "",
                    "suggestion": "",
                },
            }

        closes = [float(b.close) for b in bars]
        last = closes[-1]

        indicators = self._indicators(bars)
        supports, resistances = self._levels(bars)
        ai = self._call_ai(symbol, period, bars, indicators, supports, resistances, last)

        if ai is not None:
            source = ai.pop("source")
            analysis = {
                "trend": ai.get("trend") if ai.get("trend") in _TREND_LABEL else "neutral",
                "trend_label": _TREND_LABEL.get(str(ai.get("trend")), "震荡"),
                "confidence": self._clamp(ai.get("confidence"), 0, 100, 60),
                "summary": str(ai.get("summary") or "")[:300],
                "detail": str(ai.get("detail") or "")[:3000],
                "suggestion": str(ai.get("suggestion") or "")[:500],
            }
            ai_supports = self._validate_levels(ai.get("supports"), last, 0.80, 1.0)
            ai_resistances = self._validate_levels(ai.get("resistances"), last, 1.0, 1.25)
            # prefer AI levels, fill with local detection when AI omitted them
            if ai_supports:
                supports = ai_supports
            if ai_resistances:
                resistances = ai_resistances
        else:
            source = "local"
            analysis = self._local_analysis(indicators, supports, resistances, last)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "period": period,
            "source": source,
            "price": self._price_block(bars),
            "indicators": indicators,
            "levels": {"supports": supports, "resistances": resistances},
            "analysis": analysis,
        }

    # ── data access ──────────────────────────────────────────────────

    def _fresh_bars(self, symbol: str, period: str, count: int) -> list[Any]:
        svc = getattr(self._store, "kline_service", None)
        if svc is None:
            return []
        bars = svc.get_klines(symbol, period, count=count) or []
        period_ms = _PERIOD_MS.get(period, 3_600_000)
        now_ms = int(time.time() * 1000)
        if not bars or (now_ms - bars[-1].open_time) > (period_ms * 3 + 120_000):
            try:
                bars = svc.fetch_history(symbol, period, limit=max(count, 200)) or bars
            except Exception:
                logger.warning("kline fetch_history failed for %s %s", symbol, period)
        return bars[-count:]

    def _price_block(self, bars: list[Any]) -> dict[str, Any]:
        closes = [float(b.close) for b in bars]
        window = bars[-24:] if len(bars) >= 24 else bars
        first = float(window[0].open)
        last = closes[-1]
        return {
            "last": round(last, 6),
            "change_pct": round((last - first) / first * 100.0, 2) if first else 0.0,
            "range_high": round(max(float(b.high) for b in window), 6),
            "range_low": round(min(float(b.low) for b in window), 6),
        }

    # ── indicators ───────────────────────────────────────────────────

    def _indicators(self, bars: list[Any]) -> dict[str, Any]:
        closes = [float(b.close) for b in bars]
        vols = [float(b.volume) for b in bars]
        last = closes[-1]

        ma7, ma25, ma99 = _sma(closes, 7), _sma(closes, 25), _sma(closes, 99)
        rsi = _rsi(closes)
        dif, dea, hist = _macd(closes)
        upper, mid, lower = _boll(closes)
        atr = _atr(bars)
        vol_avg = _sma(vols, 20)
        vol_ratio = (vols[-1] / vol_avg) if vol_avg else None

        if ma7 and ma25 and ma99:
            if ma7 > ma25 > ma99:
                ma_trend = "多头排列"
            elif ma7 < ma25 < ma99:
                ma_trend = "空头排列"
            else:
                ma_trend = "均线纠缠"
        else:
            ma_trend = "样本不足"

        percent_b = None
        if upper is not None and lower is not None and upper != lower:
            percent_b = (last - lower) / (upper - lower)

        return {
            "ma7": self._round(ma7),
            "ma25": self._round(ma25),
            "ma99": self._round(ma99),
            "ma_trend": ma_trend,
            "rsi14": self._round(rsi),
            "macd": {
                "dif": self._round(dif),
                "dea": self._round(dea),
                "hist": self._round(hist),
            },
            "boll": {
                "upper": self._round(upper),
                "mid": self._round(mid),
                "lower": self._round(lower),
                "percent_b": self._round(percent_b),
            },
            "atr14": self._round(atr),
            "atr_pct": self._round(atr / last * 100.0 if atr and last else None),
            "vol_ratio": self._round(vol_ratio),
        }

    # ── support / resistance detection ───────────────────────────────

    def _levels(self, bars: list[Any], window: int = 3, tolerance: float = 0.006) -> tuple[list[dict], list[dict]]:
        highs = [float(b.high) for b in bars]
        lows = [float(b.low) for b in bars]
        closes = [float(b.close) for b in bars]
        last = closes[-1]

        pivots_high: list[tuple[int, float]] = []
        pivots_low: list[tuple[int, float]] = []
        for i in range(window, len(bars) - window):
            seg_h = highs[i - window : i + window + 1]
            seg_l = lows[i - window : i + window + 1]
            if highs[i] == max(seg_h):
                pivots_high.append((i, highs[i]))
            if lows[i] == min(seg_l):
                pivots_low.append((i, lows[i]))

        def cluster(points: list[tuple[int, float]]) -> list[dict]:
            clusters: list[dict] = []
            for idx, price in points:
                for c in clusters:
                    if abs(price - c["price"]) / c["price"] < tolerance:
                        c["price"] = (c["price"] * c["touches"] + price) / (c["touches"] + 1)
                        c["touches"] += 1
                        c["last_idx"] = max(c["last_idx"], idx)
                        break
                else:
                    clusters.append({"price": price, "touches": 1, "last_idx": idx})
            return clusters

        def pick(clusters: list[dict], below: bool) -> list[dict]:
            side = [c for c in clusters if (c["price"] < last) == below]
            # score: touch count dominant, recency bonus; keep top 3
            side.sort(key=lambda c: (c["touches"], c["last_idx"]), reverse=True)
            top = side[:3]
            top.sort(key=lambda c: c["price"], reverse=not below)
            return [
                {"price": round(c["price"], 6), "strength": c["touches"]}
                for c in top
            ]

        return pick(cluster(pivots_low), below=True), pick(cluster(pivots_high), below=False)

    # ── LLM call ─────────────────────────────────────────────────────

    def _call_ai(
        self,
        symbol: str,
        period: str,
        bars: list[Any],
        indicators: dict[str, Any],
        supports: list[dict],
        resistances: list[dict],
        last: float,
    ) -> dict[str, Any] | None:
        ai_service = getattr(self._store, "ai_service", None)
        if ai_service is None:
            return None

        provider_id = "stepfun"
        try:
            control = getattr(self._store, "control_service", None)
            if control is not None and not control.get_model_provider("stepfun"):
                provider_id = "deepseek"
        except Exception:
            pass

        rows = []
        for b in bars[-48:]:
            ts = datetime.fromtimestamp(b.open_time / 1000, tz=timezone.utc).strftime("%m-%d %H:%M")
            rows.append(f"{ts},{float(b.open):.4g},{float(b.high):.4g},{float(b.low):.4g},{float(b.close):.4g},{float(b.volume):.6g}")

        prompt = self._build_prompt(symbol, period, rows, indicators, supports, resistances, last)

        try:
            resp = ai_service.chat(
                provider_id=provider_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2200,
                timeout=90.0,
            )
            content = str(resp.get("content", "") or "")
            data = self._extract_json(content)
            if not isinstance(data, dict):
                logger.warning(
                    "kline analysis: LLM returned non-JSON (%s), head=%r",
                    provider_id,
                    content[:200],
                )
                return None
            data["source"] = str(resp.get("model") or provider_id)
            return data
        except Exception as exc:
            logger.warning("kline analysis LLM call failed: %s", exc)
            return None

    def _build_prompt(
        self,
        symbol: str,
        period: str,
        rows: list[str],
        indicators: dict[str, Any],
        supports: list[dict],
        resistances: list[dict],
        last: float,
    ) -> str:
        sup = ", ".join(str(s["price"]) for s in supports) or "无"
        res = ", ".join(str(r["price"]) for r in resistances) or "无"
        return (
            f"你是专业加密货币技术分析师。请基于以下 {symbol} {period} 周期的真实K线数据与本地精确计算的指标，输出结构化技术分析。\n\n"
            f"【最近48根K线 (时间,开,高,低,收,量)】\n" + "\n".join(rows) + "\n\n"
            f"【本地精确计算指标】\n"
            f"- 最新价: {last}\n"
            f"- MA7/MA25/MA99: {indicators.get('ma7')}/{indicators.get('ma25')}/{indicators.get('ma99')} ({indicators.get('ma_trend')})\n"
            f"- RSI14: {indicators.get('rsi14')}\n"
            f"- MACD(DIF/DEA/HIST): {indicators.get('macd')}\n"
            f"- BOLL(上/中/下/%B): {indicators.get('boll')}\n"
            f"- ATR14: {indicators.get('atr14')} (占比 {indicators.get('atr_pct')}%)\n"
            f"- 量比(相对20期均量): {indicators.get('vol_ratio')}\n\n"
            f"【本地摆动点检测】支撑位: {sup}; 阻力位: {res}\n\n"
            f"严格只输出一个JSON对象（不要任何其他文字、不要markdown代码块），格式：\n"
            f'{{"trend":"bullish|bearish|neutral","confidence":0-100的整数,"summary":"一句话核心结论(50字内)",'
            f'"detail":"多维度分析(趋势结构/量价/指标背离/关键位置,300字内,可用\\n分行)","suggestion":"具体操作建议(100字内,含仓位/止损参考)",'
            f'"supports":[支撑位价格,最多3个数字],"resistances":[阻力位价格,最多3个数字]}}\n'
            f"要求：supports必须低于最新价、resistances必须高于最新价，且与本地检测值偏差不超过3%；confidence代表你对趋势判断的把握。"
        )

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        text = (text or "").strip()
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
        start, end = text.find("{"), text.rfind("}")
        if start < 0:
            return None
        candidate = text[start : end + 1] if end > start else text[start:]
        try:
            data = json.loads(candidate)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            pass
        # token-truncated JSON: repair by closing open strings/brackets
        repaired = self._repair_json(candidate)
        if repaired:
            try:
                data = json.loads(repaired)
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                pass
        # last resort: salvage individual fields with regex
        salvaged = self._salvage_fields(text)
        return salvaged or None

    @staticmethod
    def _repair_json(candidate: str) -> str | None:
        out = []
        in_string = False
        escaped = False
        stack: list[str] = []
        for ch in candidate:
            if in_string:
                out.append(ch)
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                out.append(ch)
            elif ch in "{[":
                stack.append("}" if ch == "{" else "]")
                out.append(ch)
            elif ch in "}]":
                if stack:
                    stack.pop()
                out.append(ch)
            else:
                out.append(ch)
        if in_string:
            out.append('"')
        # drop a trailing dangling comma
        while out and out[-1] in ",:":
            out.pop()
        repaired = "".join(out) + "".join(reversed(stack))
        return repaired if repaired != candidate else None

    @staticmethod
    def _salvage_fields(text: str) -> dict[str, Any] | None:
        def grab(pattern: str, cast=str):
            m = re.search(pattern, text, re.DOTALL)
            if not m:
                return None
            try:
                return cast(m.group(1))
            except (TypeError, ValueError):
                return None

        trend = grab(r'"trend"\s*:\s*"([^"]+)"')
        if trend is None:
            return None
        confidence = grab(r'"confidence"\s*:\s*([0-9]+)', int)
        summary = grab(r'"summary"\s*:\s*"([^"]*)"')
        detail = grab(r'"detail"\s*:\s*"([^"]*)"')
        suggestion = grab(r'"suggestion"\s*:\s*"([^"]*)"')
        levels_txt = text[text.rfind('"supports"'):] if '"supports"' in text else ""
        sup = re.findall(r'([0-9]+(?:\.[0-9]+)?)', levels_txt.split('"resistances"')[0]) if levels_txt else []
        res = re.findall(r'([0-9]+(?:\.[0-9]+)?)', levels_txt.split('"resistances"')[1]) if '"resistances"' in levels_txt else []
        data: dict[str, Any] = {"trend": trend}
        if confidence is not None:
            data["confidence"] = confidence
        for key, val in (("summary", summary), ("detail", detail), ("suggestion", suggestion)):
            if val:
                data[key] = val
        if sup:
            data["supports"] = [float(x) for x in sup[:3]]
        if res:
            data["resistances"] = [float(x) for x in res[:3]]
        return data

    # ── validation / fallback ────────────────────────────────────────

    @staticmethod
    def _clamp(value: Any, lo: float, hi: float, default: float) -> float:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return default
        return max(lo, min(hi, v))

    def _validate_levels(self, raw: Any, last: float, lo_factor: float, hi_factor: float) -> list[dict]:
        if not isinstance(raw, list):
            return []
        out: list[dict] = []
        for item in raw[:3]:
            try:
                price = float(item)
            except (TypeError, ValueError):
                continue
            if lo_factor * last <= price <= hi_factor * last and price > 0:
                out.append({"price": round(price, 6), "strength": 0})
        out.sort(key=lambda x: x["price"], reverse=(lo_factor < 1))
        return out

    def _local_analysis(self, indicators: dict, supports: list[dict], resistances: list[dict], last: float) -> dict[str, Any]:
        rsi = indicators.get("rsi14")
        ma_trend = indicators.get("ma_trend", "样本不足")
        hist = (indicators.get("macd") or {}).get("hist")
        vol_ratio = indicators.get("vol_ratio")

        if ma_trend == "多头排列":
            trend = "bullish"
        elif ma_trend == "空头排列":
            trend = "bearish"
        else:
            trend = "neutral"

        if rsi is not None and rsi >= 70:
            rsi_txt = f"RSI14={rsi} 处于超买区，短期回调风险上升"
        elif rsi is not None and rsi <= 30:
            rsi_txt = f"RSI14={rsi} 处于超卖区，存在技术性反弹动能"
        elif rsi is not None:
            rsi_txt = f"RSI14={rsi} 处于中性区间"
        else:
            rsi_txt = "RSI 样本不足"

        sup_txt = "、".join(str(s["price"]) for s in supports) or "暂无明确支撑"
        res_txt = "、".join(str(r["price"]) for r in resistances) or "暂无明确阻力"

        confidence = {"bullish": 65, "bearish": 65, "neutral": 50}[trend]
        if hist is not None:
            confidence += 5 if (hist > 0) == (trend == "bullish") else -5

        return {
            "trend": trend,
            "trend_label": _TREND_LABEL[trend],
            "confidence": int(self._clamp(confidence, 20, 85, 50)),
            "summary": f"均线{ma_trend}，{rsi_txt}；支撑 {sup_txt}，阻力 {res_txt}。",
            "detail": (
                f"均线结构：MA7/MA25/MA99 呈{ma_trend}，最新价 {last}。\n"
                f"动量指标：{rsi_txt}；MACD 柱状值 {hist}（{'红柱' if (hist or 0) > 0 else '绿柱'}）。\n"
                f"波动与量能：ATR14 占最新价 {indicators.get('atr_pct')}%，量比 {vol_ratio}"
                f"（{'放量' if (vol_ratio or 1) > 1.5 else '量能平稳'}）。\n"
                f"关键位置：支撑位 {sup_txt}；阻力位 {res_txt}。\n"
                f"（AI 模型暂不可用，以上为本地指标引擎自动生成）"
            ),
            "suggestion": (
                f"{'多单可持有，关注突破 ' + res_txt if trend == 'bullish' else ('空单可持有，关注跌破 ' + sup_txt if trend == 'bearish' else '区间思路，靠近支撑/阻力再决策')}；"
                "建议以 ATR14 的 1.5 倍作为止损参考。"
            ),
        }

    @staticmethod
    def _round(v: Any, nd: int = 4) -> float | None:
        if v is None:
            return None
        try:
            return round(float(v), nd)
        except (TypeError, ValueError):
            return None
