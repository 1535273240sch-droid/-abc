"""Deterministic Paper Exchange Adapter.

No real network, no real API keys, no live trading.
All outputs are deterministic based on SHA-256 of input parameters.
"""

import hashlib
import uuid
from decimal import Decimal
from typing import Any

from app.adapters.protocol import (
    AdapterOrderStatus,
    ExchangeAdapter,
    OrderResult,
    StandardSymbol,
    StandardTicker,
    utcnow,
)


class PaperExchangeAdapter(ExchangeAdapter):
    """Simulates an exchange adapter in paper mode.

    All order operations are deterministic and generate results based on
    SHA-256 hash of the input parameters. No real network calls are made.
    """

    def __init__(self, name: str = "paper"):
        self._name = name
        self._orders: dict[str, dict[str, Any]] = {}
        self._symbols = [
            StandardSymbol("BTCUSDT", "BTC", "USDT", "spot", "trading"),
            StandardSymbol("ETHUSDT", "ETH", "USDT", "spot", "trading"),
            StandardSymbol("BNBUSDT", "BNB", "USDT", "spot", "trading"),
            StandardSymbol("SOLUSDT", "SOL", "USDT", "spot", "trading"),
        ]
        self._tickers = {
            "BTCUSDT": StandardTicker("BTCUSDT", self._name, "100000.12", "100000.10", "100000.14", "12345.67", utcnow(), 1001),
            "ETHUSDT": StandardTicker("ETHUSDT", self._name, "3500.50", "3500.45", "3500.55", "67890.12", utcnow(), 2001),
            "BNBUSDT": StandardTicker("BNBUSDT", self._name, "580.30", "580.25", "580.35", "1234.56", utcnow(), 3001),
            "SOLUSDT": StandardTicker("SOLUSDT", self._name, "145.20", "145.15", "145.25", "5678.90", utcnow(), 4001),
        }

    def connect(self) -> Any:
        return None

    def disconnect(self) -> Any:
        return None

    def health(self) -> Any:
        return None

    def get_symbols(self) -> list[StandardSymbol]:
        return list(self._symbols)

    def get_ticker(self, symbol: str) -> StandardTicker:
        return self._tickers.get(symbol, self._tickers["BTCUSDT"])

    def _hash_input(self, client_order_id: str, symbol: str, side: str, quantity: str, price: str | None) -> str:
        seed = f"{client_order_id}:{symbol}:{side}:{quantity}:{price or 'market'}:paper"
        return hashlib.sha256(seed.encode()).hexdigest()

    def place_order(self, client_order_id: str, symbol: str, side: str, quantity: str, price: str | None) -> OrderResult:
        digest = self._hash_input(client_order_id, symbol, side, quantity, price)
        fill_ratio = (int(digest[:4], 16) % 100) / 100.0
        is_filled = fill_ratio > 0.1
        is_partial = 0.1 < fill_ratio < 0.95

        if is_partial:
            filled_qty = str((Decimal(quantity) * Decimal(str(fill_ratio))).quantize(Decimal("0.00000001")))
        elif is_filled:
            filled_qty = quantity
        else:
            filled_qty = "0.00000000"

        order = {
            "client_order_id": client_order_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "filled_quantity": filled_qty,
            "average_price": price or "0.00",
            "status": AdapterOrderStatus.FILLED if is_filled else (AdapterOrderStatus.PARTIALLY_FILLED if is_partial else AdapterOrderStatus.NEW),
            "text": f"Paper simulated order for {symbol}",
            "created_at": utcnow(),
        }
        self._orders[client_order_id] = order

        return OrderResult(
            client_order_id=client_order_id,
            exchange=self._name,
            status=order["status"],
            filled_quantity=order["filled_quantity"],
            average_price=order["average_price"],
            text=order["text"],
        )

    def cancel_order(self, client_order_id: str) -> OrderResult:
        existing = self._orders.get(client_order_id)
        if existing:
            existing["status"] = AdapterOrderStatus.CANCELLED
            existing["text"] = "Cancelled by paper adapter"
        return OrderResult(
            client_order_id=client_order_id,
            exchange=self._name,
            status=AdapterOrderStatus.CANCELLED,
            filled_quantity=existing["filled_quantity"] if existing else "0.00000000",
            average_price=existing.get("average_price") if existing else None,
            text="Cancelled by paper adapter" if existing else "Order not found (adapter)",
        )

    def get_order_status(self, client_order_id: str) -> OrderResult:
        existing = self._orders.get(client_order_id)
        if not existing:
            return OrderResult(
                client_order_id=client_order_id,
                exchange=self._name,
                status=AdapterOrderStatus.REJECTED,
                filled_quantity="0.00000000",
                average_price=None,
                text="Order not found in paper adapter",
            )
        return OrderResult(
            client_order_id=client_order_id,
            exchange=self._name,
            status=existing["status"],
            filled_quantity=existing["filled_quantity"],
            average_price=existing.get("average_price"),
            text=existing.get("text", ""),
        )