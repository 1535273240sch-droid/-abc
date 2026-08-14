import json
import urllib.request
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from app.models.domain import Symbol, Ticker
from app.core.config import settings
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc
from app.services.market_providers import MultiSourceMarketProvider, default_providers


class MarketService:
    def __init__(self, store: Any, provider: MultiSourceMarketProvider | None = None):
        self._store = store
        self._provider = provider or MultiSourceMarketProvider(default_providers())
        self.last_refresh_at: str | None = None
        self.last_error: str | None = None
        self.last_source: str | None = None
        self.sequence = 0
        self._seed()

    def _seed(self):
        symbols = [
            Symbol("BTCUSDT", "BTC", "USDT", "spot", "0.00001", "1000.0", "0.01"),
            Symbol("ETHUSDT", "ETH", "USDT", "spot", "0.0001", "10000.0", "0.01"),
            Symbol("BNBUSDT", "BNB", "USDT", "spot", "0.001", "100000.0", "0.001"),
            Symbol("SOLUSDT", "SOL", "USDT", "spot", "0.01", "100000.0", "0.001"),
            Symbol("DOGEUSDT", "DOGE", "USDT", "spot", "1.0", "10000000.0", "0.00001"),
        ]
        for s in symbols:
            self._store.symbols[s.symbol] = s

        tickers = [
            Ticker("BTCUSDT", "100000.12", "100000.10", "100000.14", "12345.67", "+2.34", "102000.00", "98000.00"),
            Ticker("ETHUSDT", "3500.50", "3500.45", "3500.55", "67890.12", "+1.56", "3600.00", "3400.00"),
            Ticker("BNBUSDT", "580.30", "580.25", "580.35", "1234.56", "+0.89", "590.00", "570.00"),
            Ticker("SOLUSDT", "145.20", "145.15", "145.25", "5678.90", "+3.21", "150.00", "140.00"),
            Ticker("DOGEUSDT", "0.12500", "0.12490", "0.12510", "987654.32", "-1.23", "0.13000", "0.12000"),
        ]
        for t in tickers:
            self._store.tickers[t.symbol] = t

    def get_symbols(self) -> list[Symbol]:
        return list(self._store.symbols.values())

    def get_tickers(self) -> list[Ticker]:
        for ticker in self._store.tickers.values():
            if not hasattr(ticker, "source"):
                ticker.source = "seeded-paper"
            if not hasattr(ticker, "event_time"):
                ticker.event_time = None
            if not hasattr(ticker, "ingest_time"):
                ticker.ingest_time = None
            if not hasattr(ticker, "sequence"):
                ticker.sequence = None
        return list(self._store.tickers.values())

    def refresh_public_tickers(self) -> list[Ticker]:
        symbols = list(self._store.symbols.keys())
        fetched, source = self._provider.fetch_tickers(symbols)
        if fetched is None or source is None:
            raise ValueError("All market data providers failed")
        self.last_source = source

        refreshed: list[Ticker] = []
        for item in fetched:
            symbol = item.get("symbol", "")
            if symbol not in self._store.symbols:
                continue
            ticker = Ticker(
                symbol=symbol,
                last_price=str(item.get("last_price", "0")),
                bid_price=str(item.get("bid_price", item.get("last_price", "0"))),
                ask_price=str(item.get("ask_price", item.get("last_price", "0"))),
                volume_24h=str(item.get("volume_24h", "0")),
                change_24h=str(item.get("change_24h", "+0.00")),
                high_24h=str(item.get("high_24h", "0")),
                low_24h=str(item.get("low_24h", "0")),
                source=source,
                event_time=datetime.now(timezone.utc),
                ingest_time=datetime.now(timezone.utc),
                sequence=self.sequence + 1,
            )
            self._store.tickers[symbol] = ticker
            refreshed.append(ticker)

        self.sequence += 1
        self.last_refresh_at = datetime.now(timezone.utc).isoformat()
        self.last_error = None
        event_bus.publish(DomainEvent(
            event_type=event_type("market", "snapshot_refreshed"),
            event_id=new_event_id("market"),
            event_time=now_utc(),
            version=1,
            resource_type="market_snapshot",
            resource_id=str(self.sequence),
            payload={"symbol_count": len(refreshed), "sequence": self.sequence, "source": source, "providers": self._provider.provider_names},
        ))
        return refreshed

    def record_refresh_error(self, exc: Exception) -> None:
        self.last_error = str(exc)[:500]

    def health(self) -> dict[str, Any]:
        quality = self.sync_quality_alerts()
        return {
            "mode": settings.market_data_mode,
            "last_refresh_at": self.last_refresh_at,
            "last_source": self.last_source,
            "last_error": self.last_error,
            "sequence": self.sequence,
            "providers": self._provider.provider_names,
            "quality": quality,
        }

    def sync_quality_alerts(self) -> dict[str, Any]:
        quality = self.quality()
        self._store.alert_service.sync_market_quality(quality)
        return quality

    def quality(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        issues: list[dict[str, Any]] = []
        expected = set(self._store.symbols)
        actual = set(self._store.tickers)
        missing = sorted(expected - actual)
        if missing:
            issues.append({"code": "MISSING_TICKERS", "symbols": missing})

        invalid: list[str] = []
        crossed: list[str] = []
        for symbol in sorted(actual & expected):
            ticker = self._store.tickers[symbol]
            try:
                last = Decimal(getattr(ticker, "last_price", "0"))
                bid = Decimal(getattr(ticker, "bid_price", "0"))
                ask = Decimal(getattr(ticker, "ask_price", "0"))
                if last <= 0 or bid <= 0 or ask <= 0:
                    invalid.append(symbol)
                if ask < bid:
                    crossed.append(symbol)
            except Exception:
                invalid.append(symbol)
        if invalid:
            issues.append({"code": "INVALID_PRICES", "symbols": sorted(set(invalid))})
        if crossed:
            issues.append({"code": "CROSSED_BOOK", "symbols": sorted(set(crossed))})
        if settings.market_data_mode == "public" and self.last_refresh_at is None:
            issues.append({"code": "PUBLIC_FEED_UNAVAILABLE" if self.last_error else "PUBLIC_FEED_NOT_READY", "message": self.last_error or "Public feed has not completed its first refresh"})
        elif settings.market_data_mode == "public" and self.last_error:
            issues.append({"code": "PUBLIC_FEED_UNAVAILABLE", "message": self.last_error})

        status = "healthy" if not issues else "degraded"
        return {
            "status": status,
            "usable": bool(actual & expected) and not invalid,
            "checked_at": now.isoformat(),
            "symbol_count": len(expected),
            "ticker_count": len(actual & expected),
            "issues": issues,
        }

    def get_order_book(self, symbol: str, depth: int = 5) -> dict[str, Any]:
        ticker = self._store.tickers.get(symbol)
        if not ticker:
            from app.core.errors import QuantError
            raise QuantError("NOT_FOUND", f"Ticker {symbol} not found", status_code=404)
        bid = Decimal(ticker.bid_price)
        ask = Decimal(ticker.ask_price)
        tick_size = Decimal(self._store.symbols[symbol].tick_size)
        bids = [[str((bid - tick_size * i).quantize(tick_size)), str((Decimal("0.1") * (i + 1)).quantize(Decimal("0.0001")))] for i in range(depth)]
        asks = [[str((ask + tick_size * i).quantize(tick_size)), str((Decimal("0.08") * (i + 1)).quantize(Decimal("0.0001")))] for i in range(depth)]
        return {"symbol": symbol, "source": getattr(ticker, "source", "seeded-paper"), "updated_at": getattr(ticker, "ingest_time", None) or datetime.now(timezone.utc), "bids": bids, "asks": asks}

    def get_trades(self, symbol: str, limit: int = 10) -> list[dict[str, Any]]:
        ticker = self._store.tickers.get(symbol)
        if not ticker:
            from app.core.errors import QuantError
            raise QuantError("NOT_FOUND", f"Ticker {symbol} not found", status_code=404)
        now = datetime.now(timezone.utc)
        price = Decimal(ticker.last_price)
        return [{"trade_id": f"paper-trade-{symbol.lower()}-{i}", "symbol": symbol, "price": str(price), "quantity": str((Decimal("0.01") * (i + 1)).quantize(Decimal("0.0001"))), "side": "buy" if i % 2 == 0 else "sell", "time": now} for i in range(min(limit, 20))]

    def get_funding_rates(self) -> list[dict[str, Any]]:
        result = []
        for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            ticker = self._store.tickers.get(symbol)
            change = Decimal(str(getattr(ticker, "change_24h", "0")).replace("+", "")) if ticker else Decimal("0")
            rate = (change / Decimal("100000")).quantize(Decimal("0.0001"))
            result.append({"symbol": f"{symbol}-PERP", "rate": f"{rate:+f}%", "predicted_rate": f"{(rate * Decimal("1.1")).quantize(Decimal("0.0001")):+f}%", "next_settlement": "Paper / N/A", "open_interest": "Paper / N/A", "open_interest_change": "Paper / N/A", "source": "paper-derived"})
        return result
