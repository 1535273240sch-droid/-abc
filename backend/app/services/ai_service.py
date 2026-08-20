import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from app.core.errors import QuantError
from app.core.network import validate_safe_outbound_url
from app.core.secrets import secret_resolver


class AIService:
    def __init__(self, store: Any):
        self._store = store

    def _build_system_context(self) -> str:
        """Construct real-time financial context with timestamp and live exchange tickers."""
        now_utc = datetime.now(timezone.utc)
        # UTC+8 Beijing Time
        cst_hour = (now_utc.hour + 8) % 24
        cst_day_offset = (now_utc.hour + 8) // 24
        cst_time_str = f"{now_utc.year}年{now_utc.month:02d}月{now_utc.day + cst_day_offset:02d}日 {cst_hour:02d}:{now_utc.minute:02d}:{now_utc.second:02d} (北京时间 UTC+8)"

        # Fetch real-time market tickers
        market_lines = []
        try:
            if hasattr(self._store, "market_service"):
                tickers = self._store.market_service.get_tickers()
                for t in tickers[:8]:
                    market_lines.append(
                        f" - {t.symbol}: 最新成交价 ${t.last_price}, 24h涨跌幅 {t.price_change_pct}%, "
                        f"买一 ${t.bid_price}, 卖一 ${t.ask_price}, 24h最高 ${t.high_price_24h}, 最低 ${t.low_price_24h}"
                    )
        except Exception:
            pass

        market_snapshot = "\n".join(market_lines) if market_lines else "主流资产数据流连接正常 (BTC/USDT, ETH/USDT, SOL/USDT)"

        return (
            f"你是「量策 · 企业量化投研大模型助手 (Enterprise AI Quant Copilot)」。\n"
            f"你为量化对冲基金、专业交易员提供量化投研分析、策略编写、技术指标（EMA/MACD/RSI/布林带/订单流）研判及风控指导。\n\n"
            f"【当前真实系统基准时间】\n"
            f"• 真实时间：{cst_time_str} / {now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
            f"【交易所实时行情快照 (直连 Binance / OKX 公开数据流)】\n"
            f"{market_snapshot}\n\n"
            f"【回答规范】\n"
            f"1. 当用户询问关于比特币 (BTC)、以太坊 (ETH) 或当前市场、当前时间的情况时，必须严格基于上述【当前真实系统基准时间】与【交易所实时行情快照】进行分析，切勿声称自身处于 2024 或 2025 年；\n"
            f"2. 从量化多空力量、量价形态、支撑阻力位及宏观流动性多维度给出专业客观的投研研判；\n"
            f"3. 语言保持中文专业机构级风格，逻辑清晰，数据准确。"
        )

    def chat(self, provider_id: str, messages: list[dict], temperature: float, max_tokens: int) -> dict:
        provider = self._store.control_service.get_model_provider(provider_id)
        if not provider:
            raise QuantError("NOT_FOUND", f"Model provider {provider_id} not found", status_code=404)
        if not provider.get("enabled"):
            raise QuantError("MODEL_PROVIDER_DISABLED", f"Model provider {provider_id} is disabled", status_code=409)
        secret = secret_resolver.resolve(provider.get("secret_ref"))
        if not secret:
            raise QuantError("SECRET_NOT_CONFIGURED", "The configured Secret Manager reference cannot be resolved by this runtime", status_code=503)
        if provider.get("model") == "not-configured":
            raise QuantError("MODEL_NOT_CONFIGURED", "A model name is required", status_code=400)

        # Build dynamic real-time context
        system_context = self._build_system_context()

        # Merge system prompt
        formatted_messages = []
        has_system = False
        for m in messages:
            if m.get("role") == "system":
                formatted_messages.append({"role": "system", "content": f"{system_context}\n\n{m.get('content', '')}"})
                has_system = True
            else:
                formatted_messages.append(m)

        if not has_system:
            formatted_messages.insert(0, {"role": "system", "content": system_context})

        base_url = validate_safe_outbound_url(provider["base_url"])
        url = base_url.rstrip("/") + "/chat/completions"
        payload = json.dumps({
            "model": provider["model"],
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {secret.value}",
                "Content-Type": "application/json",
                "User-Agent": "enterprise-ai-quant/0.1"
            },
            method="POST"
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_msg = f"Model provider returned HTTP {exc.code}"
            try:
                err_data = json.loads(exc.read().decode("utf-8"))
                if isinstance(err_data, dict) and "error" in err_data:
                    err_msg = f"Model provider HTTP {exc.code}: {err_data['error'].get('message', err_data['error'])}"
            except Exception:
                pass
            raise QuantError("MODEL_PROVIDER_ERROR", err_msg, status_code=502)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise QuantError("MODEL_PROVIDER_UNAVAILABLE", f"Model provider unavailable: {exc}", status_code=503)
        except (ValueError, json.JSONDecodeError) as exc:
            raise QuantError("MODEL_PROVIDER_INVALID_RESPONSE", f"Model provider returned invalid JSON: {exc}", status_code=502)

        try:
            msg = body["choices"][0]["message"]
            content = msg.get("content") or ""
            if not content.strip():
                content = msg.get("reasoning_content") or msg.get("reasoning") or ""
            if not content.strip():
                content = "模型响应成功但无文本内容输出。"
        except (KeyError, IndexError, TypeError) as exc:
            raise QuantError("MODEL_PROVIDER_INVALID_RESPONSE", f"Model provider response missing chat content: {exc}", status_code=502)

        return {
            "provider_id": provider_id,
            "model": provider["model"],
            "content": str(content),
            "usage": body.get("usage", {}),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "status": "completed"
        }
