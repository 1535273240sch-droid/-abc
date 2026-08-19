"""Multi-source market data providers with automatic failover.

Each provider fetches tickers, order book depth, trades, and funding
rates for a list of symbols from a public exchange API. The
``MultiSourceMarketProvider`` tries providers in order and falls back
to the next on failure, returning the source name alongside the data so
callers can record provenance.

New sources can be added by implementing :class:`MarketDataProvider`
and appending it to the provider chain in :func:`default_providers`.
"""

import json
import logging
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


class MarketDataProvider(ABC):
    """Abstract public market data provider."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier used in Ticker.source and logs."""
        ...

    @abstractmethod
    def fetch_tickers(self, symbols: list[str]) -> list[dict[str, Any]] | None:
        """Fetch tickers for *symbols*."""
        ...

    def fetch_order_book(self, symbol: str, depth: int = 20) -> dict[str, Any] | None:
        """Fetch order book depth for *symbol*."""
        return None

    def fetch_trades(self, symbol: str, limit: int = 20) -> list[dict[str, Any]] | None:
        """Fetch recent trades for *symbol*."""
        return None

    def fetch_funding_rates(self) -> list[dict[str, Any]] | None:
        """Fetch perpetual contract funding rates."""
        return None


class BinancePublicProvider(MarketDataProvider):
    """Binance public 24-hour ticker, depth, trades, and funding rate endpoint."""

    @property
    def name(self) -> str:
        return "binance-public"

    def fetch_tickers(self, symbols: list[str]) -> list[dict[str, Any]] | None:
        from urllib.parse import quote

        encoded = quote(json.dumps(symbols, separators=(",", ":")))
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbols={encoded}"
        request = urllib.request.Request(url, headers={"User-Agent": "enterprise-ai-quant/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Binance public fetch failed: %s", exc)
            return None
        if not isinstance(payload, list):
            logger.warning("Binance public returned non-list payload")
            return None
        result = []
        for item in payload:
            symbol = str(item.get("symbol", ""))
            if symbol not in symbols:
                continue
            change = Decimal(str(item.get("priceChangePercent", "0"))).quantize(Decimal("0.01"))
            result.append({
                "symbol": symbol,
                "last_price": str(item.get("lastPrice", "0")),
                "bid_price": str(item.get("bidPrice", item.get("lastPrice", "0"))),
                "ask_price": str(item.get("askPrice", item.get("lastPrice", "0"))),
                "volume_24h": str(item.get("volume", "0")),
                "change_24h": f"{change:+f}",
                "high_24h": str(item.get("highPrice", "0")),
                "low_24h": str(item.get("lowPrice", "0")),
            })
        return result if result else None

    def fetch_order_book(self, symbol: str, depth: int = 20) -> dict[str, Any] | None:
        limit = min(max(depth, 5), 50)
        url = f"https://api.binance.com/api/v3/depth?symbol={symbol}&limit={limit}"
        request = urllib.request.Request(url, headers={"User-Agent": "enterprise-ai-quant/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Binance depth fetch failed for %s: %s", symbol, exc)
            return None
        if not isinstance(payload, dict):
            return None
        bids = [[str(p), str(q)] for p, q in payload.get("bids", [])[:depth]]
        asks = [[str(p), str(q)] for p, q in payload.get("asks", [])[:depth]]
        return {
            "symbol": symbol,
            "source": self.name,
            "updated_at": datetime.now(timezone.utc),
            "bids": bids,
            "asks": asks,
        }

    def fetch_trades(self, symbol: str, limit: int = 20) -> list[dict[str, Any]] | None:
        fetch_limit = min(max(limit, 5), 50)
        url = f"https://api.binance.com/api/v3/trades?symbol={symbol}&limit={fetch_limit}"
        request = urllib.request.Request(url, headers={"User-Agent": "enterprise-ai-quant/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Binance trades fetch failed for %s: %s", symbol, exc)
            return None
        if not isinstance(payload, list):
            return None
        trades = []
        for item in payload[:limit]:
            ts = item.get("time", 0)
            trades.append({
                "trade_id": str(item.get("id", "")),
                "symbol": symbol,
                "price": str(item.get("price", "0")),
                "quantity": str(item.get("qty", "0")),
                "side": "sell" if item.get("isBuyerMaker") else "buy",
                "time": datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc) if ts else datetime.now(timezone.utc),
            })
        return trades if trades else None

    def fetch_funding_rates(self) -> list[dict[str, Any]] | None:
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        request = urllib.request.Request(url, headers={"User-Agent": "enterprise-ai-quant/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Binance funding fetch failed: %s", exc)
            return None
        if not isinstance(payload, list):
            return None
        tracked = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"}
        results = []
        for item in payload:
            sym = str(item.get("symbol", ""))
            if sym in tracked:
                try:
                    last_rate = Decimal(str(item.get("lastFundingRate", "0")))
                    rate_pct = f"{(last_rate * 100):+.4f}%"
                    pred_rate = Decimal(str(item.get("interestRate", "0.0001"))) + last_rate
                    pred_pct = f"{(pred_rate * 100):+.4f}%"
                except Exception:
                    rate_pct = "+0.0100%"
                    pred_pct = "+0.0100%"
                nxt_time = item.get("nextFundingTime")
                next_settlement = (
                    datetime.fromtimestamp(nxt_time / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    if nxt_time
                    else "N/A"
                )
                results.append({
                    "symbol": f"{sym}-PERP",
                    "rate": rate_pct,
                    "predicted_rate": pred_pct,
                    "next_settlement": next_settlement,
                    "open_interest": "N/A",
                    "open_interest_change": "+0.00%",
                    "source": self.name,
                })
        return results if results else None


class CoinbasePublicProvider(MarketDataProvider):
    """Coinbase public ticker endpoint (fallback source)."""

    @property
    def name(self) -> str:
        return "coinbase-public"

    def fetch_tickers(self, symbols: list[str]) -> list[dict[str, Any]] | None:
        coinbase_products = []
        symbol_map: dict[str, str] = {}
        for sym in symbols:
            if sym.endswith("USDT"):
                base = sym[:-4]
                product = f"{base}-USD"
                coinbase_products.append(product)
                symbol_map[product] = sym
            else:
                coinbase_products.append(sym)
                symbol_map[sym] = sym

        results = []
        for product in coinbase_products:
            url = f"https://api.exchange.coinbase.com/products/{product}/ticker"
            request = urllib.request.Request(url, headers={"User-Agent": "enterprise-ai-quant/0.1"})
            try:
                with urllib.request.urlopen(request, timeout=8) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Coinbase fetch failed for %s: %s", product, exc)
                return None
            if not isinstance(payload, dict):
                return None
            original_symbol = symbol_map.get(product, product)
            last_price = str(payload.get("price", "0"))
            bid = str(payload.get("bid", last_price))
            ask = str(payload.get("ask", last_price))
            volume = str(payload.get("volume", "0"))
            results.append({
                "symbol": original_symbol,
                "last_price": last_price,
                "bid_price": bid or last_price,
                "ask_price": ask or last_price,
                "volume_24h": volume,
                "change_24h": "+0.00",
                "high_24h": last_price,
                "low_24h": last_price,
            })
        return results if results else None

    def fetch_order_book(self, symbol: str, depth: int = 20) -> dict[str, Any] | None:
        product = f"{symbol[:-4]}-USD" if symbol.endswith("USDT") else symbol
        url = f"https://api.exchange.coinbase.com/products/{product}/book?level=2"
        request = urllib.request.Request(url, headers={"User-Agent": "enterprise-ai-quant/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Coinbase orderbook fetch failed for %s: %s", product, exc)
            return None
        if not isinstance(payload, dict):
            return None
        bids = [[str(p), str(q)] for p, q, *_ in payload.get("bids", [])[:depth]]
        asks = [[str(p), str(q)] for p, q, *_ in payload.get("asks", [])[:depth]]
        return {
            "symbol": symbol,
            "source": self.name,
            "updated_at": datetime.now(timezone.utc),
            "bids": bids,
            "asks": asks,
        }

    def fetch_trades(self, symbol: str, limit: int = 20) -> list[dict[str, Any]] | None:
        product = f"{symbol[:-4]}-USD" if symbol.endswith("USDT") else symbol
        url = f"https://api.exchange.coinbase.com/products/{product}/trades?limit={min(max(limit, 5), 50)}"
        request = urllib.request.Request(url, headers={"User-Agent": "enterprise-ai-quant/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Coinbase trades fetch failed for %s: %s", product, exc)
            return None
        if not isinstance(payload, list):
            return None
        trades = []
        for item in payload[:limit]:
            time_str = item.get("time")
            dt = datetime.fromisoformat(time_str.replace("Z", "+00:00")) if time_str else datetime.now(timezone.utc)
            trades.append({
                "trade_id": str(item.get("trade_id", "")),
                "symbol": symbol,
                "price": str(item.get("price", "0")),
                "quantity": str(item.get("size", "0")),
                "side": str(item.get("side", "buy")).lower(),
                "time": dt,
            })
        return trades if trades else None


class OkxPublicProvider(MarketDataProvider):
    """OKX public ticker, depth, trades, and funding rate endpoint (second fallback)."""

    @property
    def name(self) -> str:
        return "okx-public"

    def fetch_tickers(self, symbols: list[str]) -> list[dict[str, Any]] | None:
        okx_ids = []
        symbol_map: dict[str, str] = {}
        for sym in symbols:
            if sym.endswith("USDT"):
                base = sym[:-4]
                inst_id = f"{base}-USDT"
                okx_ids.append(inst_id)
                symbol_map[inst_id] = sym
            else:
                okx_ids.append(sym)
                symbol_map[sym] = sym

        url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
        request = urllib.request.Request(url, headers={"User-Agent": "enterprise-ai-quant/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("OKX public fetch failed: %s", exc)
            return None
        if not isinstance(payload, dict) or payload.get("code") != "0":
            return None
        data = payload.get("data", [])
        if not isinstance(data, list):
            return None

        ticker_lookup: dict[str, dict[str, str]] = {}
        for item in data:
            inst_id = item.get("instId", "")
            ticker_lookup[inst_id] = item

        results = []
        for inst_id in okx_ids:
            item = ticker_lookup.get(inst_id)
            if not item:
                continue
            original_symbol = symbol_map.get(inst_id, inst_id)
            change = Decimal(str(item.get("last", "0"))).quantize(Decimal("0.01"))
            results.append({
                "symbol": original_symbol,
                "last_price": str(item.get("last", "0")),
                "bid_price": str(item.get("bidPx", item.get("last", "0"))),
                "ask_price": str(item.get("askPx", item.get("last", "0"))),
                "volume_24h": str(item.get("vol24h", item.get("volCcy24h", "0"))),
                "change_24h": f"{change:+f}",
                "high_24h": str(item.get("high24h", item.get("last", "0"))),
                "low_24h": str(item.get("low24h", item.get("last", "0"))),
            })
        return results if results else None

    def fetch_order_book(self, symbol: str, depth: int = 20) -> dict[str, Any] | None:
        inst_id = f"{symbol[:-4]}-USDT" if symbol.endswith("USDT") else symbol
        url = f"https://www.okx.com/api/v5/market/books?instId={inst_id}&sz={min(max(depth, 5), 50)}"
        request = urllib.request.Request(url, headers={"User-Agent": "enterprise-ai-quant/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("OKX orderbook fetch failed for %s: %s", inst_id, exc)
            return None
        if not isinstance(payload, dict) or payload.get("code") != "0":
            return None
        data = payload.get("data", [])
        if not data:
            return None
        book = data[0]
        bids = [[str(p[0]), str(p[1])] for p in book.get("bids", [])[:depth]]
        asks = [[str(p[0]), str(p[1])] for p in book.get("asks", [])[:depth]]
        return {
            "symbol": symbol,
            "source": self.name,
            "updated_at": datetime.now(timezone.utc),
            "bids": bids,
            "asks": asks,
        }

    def fetch_trades(self, symbol: str, limit: int = 20) -> list[dict[str, Any]] | None:
        inst_id = f"{symbol[:-4]}-USDT" if symbol.endswith("USDT") else symbol
        url = f"https://www.okx.com/api/v5/market/trades?instId={inst_id}&limit={min(max(limit, 5), 50)}"
        request = urllib.request.Request(url, headers={"User-Agent": "enterprise-ai-quant/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("OKX trades fetch failed for %s: %s", inst_id, exc)
            return None
        if not isinstance(payload, dict) or payload.get("code") != "0":
            return None
        data = payload.get("data", [])
        trades = []
        for item in data[:limit]:
            ts = item.get("ts")
            trades.append({
                "trade_id": str(item.get("tradeId", "")),
                "symbol": symbol,
                "price": str(item.get("px", "0")),
                "quantity": str(item.get("sz", "0")),
                "side": str(item.get("side", "buy")).lower(),
                "time": datetime.fromtimestamp(int(ts) / 1000.0, tz=timezone.utc) if ts else datetime.now(timezone.utc),
            })
        return trades if trades else None

    def fetch_funding_rates(self) -> list[dict[str, Any]] | None:
        results = []
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"):
            inst_id = f"{sym[:-4]}-USDT-SWAP" if sym.endswith("USDT") else sym
            url = f"https://www.okx.com/api/v5/public/funding-rate?instId={inst_id}"
            request = urllib.request.Request(url, headers={"User-Agent": "enterprise-ai-quant/0.1"})
            try:
                with urllib.request.urlopen(request, timeout=6) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                logger.debug("OKX funding fetch failed for %s: %s", inst_id, exc)
                continue
            if not isinstance(payload, dict) or payload.get("code") != "0":
                continue
            data = payload.get("data", [])
            if not data:
                continue
            item = data[0]
            try:
                rate_val = Decimal(str(item.get("fundingRate", "0")))
                rate_pct = f"{(rate_val * 100):+.4f}%"
                next_rate_str = item.get("nextFundingRate")
                pred_val = Decimal(str(next_rate_str)) if next_rate_str else rate_val
                pred_pct = f"{(pred_val * 100):+.4f}%"
            except Exception:
                rate_pct = "+0.0100%"
                pred_pct = "+0.0100%"
            nxt_time = item.get("nextFundingTime")
            next_settlement = (
                datetime.fromtimestamp(int(nxt_time) / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                if nxt_time
                else "N/A"
            )
            results.append({
                "symbol": f"{sym}-PERP",
                "rate": rate_pct,
                "predicted_rate": pred_pct,
                "next_settlement": next_settlement,
                "open_interest": "N/A",
                "open_interest_change": "+0.00%",
                "source": self.name,
            })
        return results if results else None


class MultiSourceMarketProvider:
    """Chain of market data providers with automatic failover.

    Tries each provider in order; the first that returns non-``None``
    wins. The source name of the last successful fetch is tracked in
    ``last_successful_source`` for observability.
    """

    def __init__(self, providers: list[MarketDataProvider]):
        self._providers = providers
        self.last_successful_source: str | None = None

    def fetch_tickers(self, symbols: list[str]) -> tuple[list[dict[str, Any]] | None, str | None]:
        """Fetch tickers, trying each provider in order."""
        for provider in self._providers:
            tickers = provider.fetch_tickers(symbols)
            if tickers is not None and len(tickers) > 0:
                self.last_successful_source = provider.name
                logger.info("Market tickers fetched from %s (%d tickers)", provider.name, len(tickers))
                return tickers, provider.name
            logger.debug("Provider %s returned no ticker data, trying next", provider.name)
        self.last_successful_source = None
        return None, None

    def fetch_order_book(self, symbol: str, depth: int = 20) -> tuple[dict[str, Any] | None, str | None]:
        """Fetch order book depth, trying each provider in order."""
        for provider in self._providers:
            book = provider.fetch_order_book(symbol, depth)
            if book is not None and (book.get("bids") or book.get("asks")):
                return book, provider.name
            logger.debug("Provider %s returned no orderbook data, trying next", provider.name)
        return None, None

    def fetch_trades(self, symbol: str, limit: int = 20) -> tuple[list[dict[str, Any]] | None, str | None]:
        """Fetch recent trades, trying each provider in order."""
        for provider in self._providers:
            trades = provider.fetch_trades(symbol, limit)
            if trades is not None and len(trades) > 0:
                return trades, provider.name
            logger.debug("Provider %s returned no trade data, trying next", provider.name)
        return None, None

    def fetch_funding_rates(self) -> tuple[list[dict[str, Any]] | None, str | None]:
        """Fetch funding rates, trying each provider in order."""
        for provider in self._providers:
            rates = provider.fetch_funding_rates()
            if rates is not None and len(rates) > 0:
                return rates, provider.name
            logger.debug("Provider %s returned no funding data, trying next", provider.name)
        return None, None

    @property
    def provider_names(self) -> list[str]:
        return [p.name for p in self._providers]


def default_providers() -> list[MarketDataProvider]:
    """Default provider chain: Binance → OKX → Coinbase."""
    return [
        BinancePublicProvider(),
        OkxPublicProvider(),
        CoinbasePublicProvider(),
    ]
