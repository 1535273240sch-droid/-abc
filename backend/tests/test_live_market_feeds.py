"""Unit tests for Live Market Feeds, MultiSource Providers, TTL Caching, and Control Service robustness."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.memory import reset_store, get_store
from app.main import app
from app.services.market_providers import (
    BinancePublicProvider,
    CoinbasePublicProvider,
    OkxPublicProvider,
    MultiSourceMarketProvider,
    default_providers,
)
from app.services.market_service import MarketService


def json_bytes(obj: Any) -> bytes:
    return json.dumps(obj).encode("utf-8")


class TestMarketDataProviders:
    """Test individual public market data providers with mocks."""

    def test_binance_provider_fetch_order_book(self):
        provider = BinancePublicProvider()
        mock_payload = {
            "lastUpdateId": 123456,
            "bids": [["64000.00", "1.5"], ["63990.00", "2.0"]],
            "asks": [["64010.00", "0.8"], ["64020.00", "1.2"]],
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json_bytes(mock_payload)
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            book = provider.fetch_order_book("BTCUSDT", depth=2)
            assert book is not None
            assert book["symbol"] == "BTCUSDT"
            assert book["source"] == "binance-public"
            assert len(book["bids"]) == 2
            assert book["bids"][0] == ["64000.00", "1.5"]
            assert len(book["asks"]) == 2

    def test_binance_provider_fetch_trades(self):
        provider = BinancePublicProvider()
        mock_payload = [
            {"id": 1001, "price": "64005.50", "qty": "0.15", "time": 1787050000000, "isBuyerMaker": False},
            {"id": 1002, "price": "64004.00", "qty": "0.20", "time": 1787050001000, "isBuyerMaker": True},
        ]
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json_bytes(mock_payload)
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            trades = provider.fetch_trades("BTCUSDT", limit=2)
            assert trades is not None
            assert len(trades) == 2
            assert trades[0]["trade_id"] == "1001"
            assert trades[0]["side"] == "buy"
            assert trades[1]["side"] == "sell"

    def test_binance_provider_fetch_funding_rates(self):
        provider = BinancePublicProvider()
        mock_payload = [
            {"symbol": "BTCUSDT", "lastFundingRate": "0.0001", "interestRate": "0.0001", "nextFundingTime": 1787068800000},
            {"symbol": "ETHUSDT", "lastFundingRate": "0.00015", "interestRate": "0.0001", "nextFundingTime": 1787068800000},
        ]
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json_bytes(mock_payload)
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            funding = provider.fetch_funding_rates()
            assert funding is not None
            assert len(funding) == 2
            assert funding[0]["symbol"] == "BTCUSDT-PERP"
            assert funding[0]["rate"] == "+0.0100%"

    def test_okx_provider_fetch_order_book(self):
        provider = OkxPublicProvider()
        mock_payload = {
            "code": "0",
            "data": [{
                "bids": [["64000.00", "1.5", "0", "1"], ["63990.00", "2.0", "0", "1"]],
                "asks": [["64010.00", "0.8", "0", "1"], ["64020.00", "1.2", "0", "1"]],
                "ts": "1787050000000",
            }]
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json_bytes(mock_payload)
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            book = provider.fetch_order_book("BTCUSDT", depth=2)
            assert book is not None
            assert book["source"] == "okx-public"
            assert len(book["bids"]) == 2
            assert book["bids"][0] == ["64000.00", "1.5"]

    def test_multi_source_provider_failover(self):
        mock_failing_p1 = MagicMock(spec=BinancePublicProvider)
        mock_failing_p1.name = "failing-binance"
        mock_failing_p1.fetch_order_book.return_value = None

        mock_working_p2 = MagicMock(spec=OkxPublicProvider)
        mock_working_p2.name = "working-okx"
        mock_working_p2.fetch_order_book.return_value = {
            "symbol": "BTCUSDT",
            "source": "working-okx",
            "updated_at": datetime.now(timezone.utc),
            "bids": [["64000", "1"]],
            "asks": [["64010", "1"]],
        }

        multi = MultiSourceMarketProvider([mock_failing_p1, mock_working_p2])
        book, src = multi.fetch_order_book("BTCUSDT", depth=10)
        assert book is not None
        assert src == "working-okx"


class TestMarketServiceCaching:
    """Test MarketService caching behavior in public mode."""

    def test_order_book_caching(self):
        store = get_store()
        mock_provider = MagicMock(spec=MultiSourceMarketProvider)
        mock_provider.fetch_order_book.return_value = ({
            "symbol": "BTCUSDT",
            "source": "mock-provider",
            "updated_at": datetime.now(timezone.utc),
            "bids": [["64000", "1"]],
            "asks": [["64010", "1"]],
        }, "mock-provider")

        ms = MarketService(store, provider=mock_provider)
        with patch.object(settings, "market_data_mode", "public"):
            book1 = ms.get_order_book("BTCUSDT", depth=5)
            book2 = ms.get_order_book("BTCUSDT", depth=5)

            assert book1["source"] == "mock-provider"
            assert book2["source"] == "mock-provider"
            # Should only call underlying provider once due to TTL cache
            assert mock_provider.fetch_order_book.call_count == 1

    def test_trades_caching(self):
        store = get_store()
        mock_provider = MagicMock(spec=MultiSourceMarketProvider)
        mock_provider.fetch_trades.return_value = ([
            {
                "trade_id": "T1",
                "symbol": "BTCUSDT",
                "price": "64000",
                "quantity": "0.1",
                "side": "buy",
                "time": datetime.now(timezone.utc),
            }
        ], "mock-provider")

        ms = MarketService(store, provider=mock_provider)
        with patch.object(settings, "market_data_mode", "public"):
            t1 = ms.get_trades("BTCUSDT", limit=5)
            t2 = ms.get_trades("BTCUSDT", limit=5)

            assert len(t1) == 1
            assert t1[0]["trade_id"] == "T1"
            assert mock_provider.fetch_trades.call_count == 1


class TestControlServiceDefensiveness:
    """Test ControlService handles partial or legacy database records."""

    def test_control_service_handles_missing_adapter_name(self):
        store = get_store()
        # Seed broken connection record without adapter_name
        store.exchange_connections["legacy-conn"] = {
            "connection_id": "binance-legacy",
            "exchange": "binance",
            "status": "disconnected",
            "config": {},
        }

        connections = store.control_service.list_exchange_connections()
        legacy = next((c for c in connections if c["connection_id"] == "binance-legacy"), None)
        assert legacy is not None
        assert legacy["adapter_name"] == "binance"
        assert legacy["environment"] == "paper"
        assert legacy["enabled"] is True
