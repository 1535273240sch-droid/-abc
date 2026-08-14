"""Multi-source market data providers with automatic failover.

Each provider fetches tickers for a list of symbols from a public
exchange API.  The ``MultiSourceMarketProvider`` tries providers in
order and falls back to the next on failure, returning the source name
alongside the data so callers can record provenance.

New sources can be added by implementing :class:`MarketDataProvider`
and appending it to the provider chain in :func:`default_providers`.
"""

import json
import logging
import urllib.request
from abc import ABC, abstractmethod
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
        """Fetch tickers for *symbols*.

        Returns a list of normalised ticker dicts (each containing at
        least ``symbol``, ``last_price``, ``bid_price``, ``ask_price``,
        ``volume_24h``, ``change_24h``, ``high_24h``, ``low_24h``), or
        ``None`` when the fetch fails.
        """
        ...


class BinancePublicProvider(MarketDataProvider):
    """Binance public 24hr ticker endpoint."""

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


class CoinbasePublicProvider(MarketDataProvider):
    """Coinbase public ticker endpoint (fallback source)."""

    @property
    def name(self) -> str:
        return "coinbase-public"

    def fetch_tickers(self, symbols: list[str]) -> list[dict[str, Any]] | None:
        # Coinbase uses product IDs like "BTC-USD"; we need to map
        # Binance-style symbols (BTCUSDT) to Coinbase-style (BTC-USD).
        coinbase_products = []
        symbol_map: dict[str, str] = {}
        for sym in symbols:
            # Strip USDT suffix, replace with USD
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
                # Coinbase doesn't provide 24h change in this endpoint
                "change_24h": "+0.00",
                "high_24h": last_price,
                "low_24h": last_price,
            })
        return results if results else None


class OkxPublicProvider(MarketDataProvider):
    """OKX public ticker endpoint (second fallback)."""

    @property
    def name(self) -> str:
        return "okx-public"

    def fetch_tickers(self, symbols: list[str]) -> list[dict[str, Any]] | None:
        # OKX uses instId like "BTC-USDT", map from Binance style
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

        # OKX batch ticker endpoint
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

        # Build a lookup by instId
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


class MultiSourceMarketProvider:
    """Chain of market data providers with automatic failover.

    Tries each provider in order; the first that returns non-``None``
    wins.  The source name of the last successful fetch is tracked in
    ``last_successful_source`` for observability.
    """

    def __init__(self, providers: list[MarketDataProvider]):
        self._providers = providers
        self.last_successful_source: str | None = None

    def fetch_tickers(self, symbols: list[str]) -> tuple[list[dict[str, Any]] | None, str | None]:
        """Fetch tickers, trying each provider in order.

        Returns ``(tickers, source_name)``.  When all providers fail,
        returns ``(None, None)``.
        """
        for provider in self._providers:
            tickers = provider.fetch_tickers(symbols)
            if tickers is not None and len(tickers) > 0:
                self.last_successful_source = provider.name
                logger.info("Market data fetched from %s (%d tickers)", provider.name, len(tickers))
                return tickers, provider.name
            logger.debug("Provider %s returned no data, trying next", provider.name)
        self.last_successful_source = None
        return None, None

    @property
    def provider_names(self) -> list[str]:
        return [p.name for p in self._providers]


def default_providers() -> list[MarketDataProvider]:
    """Default provider chain: Binance → Coinbase → OKX."""
    return [
        BinancePublicProvider(),
        CoinbasePublicProvider(),
        OkxPublicProvider(),
    ]
