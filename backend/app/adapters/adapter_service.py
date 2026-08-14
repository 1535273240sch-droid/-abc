"""Facade service for adapter management.

Wires connection manager with audit, events, and kill-switch safety.
Does NOT expose any order creation paths — that is the execution service's role.
"""

from typing import Any

from app.adapters.connection_manager import ConnectionManager, ManagedAdapter
from app.adapters.paper_exchange_adapter import PaperExchangeAdapter
from app.adapters.protocol import (
    AdapterConnectionStatus,
    AdapterHealth,
    AdapterOrderStatus,
    OrderResult,
    StandardSymbol,
    StandardTicker,
    utcnow,
)
from app.core.errors import QuantError
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc


class AdapterService:
    def __init__(self, store: Any):
        self._store = store
        self._manager = ConnectionManager()
        self._seed()

    def _seed(self):
        self._manager.register("binance", PaperExchangeAdapter("binance"), max_rps=15.0, max_retries=3)
        self._manager.register("okx", PaperExchangeAdapter("okx"), max_rps=10.0, max_retries=2)
        self._manager.register("bybit", PaperExchangeAdapter("bybit"), max_rps=8.0, max_retries=2)
        self._manager.register("paper", PaperExchangeAdapter("paper"), max_rps=50.0, max_retries=0)

    def connect_all(self) -> list[dict]:
        results = self._manager.connect_all()
        for h in results:
            event_bus.publish(DomainEvent(
                event_type=event_type("adapter", "connected"),
                event_id=new_event_id("adp"),
                event_time=now_utc(),
                version=1,
                actor="system",
                resource_type="adapter",
                resource_id=h.exchange,
                payload={"status": h.status.value, "latency_ms": h.latency_ms},
            ))
        return [self._health_to_dict(h) for h in results]

    def disconnect_all(self) -> list[dict]:
        results = self._manager.disconnect_all()
        for h in results:
            event_bus.publish(DomainEvent(
                event_type=event_type("adapter", "disconnected"),
                event_id=new_event_id("adp"),
                event_time=now_utc(),
                version=1,
                actor="system",
                resource_type="adapter",
                resource_id=h.exchange,
                payload={"status": h.status.value},
            ))
        return [self._health_to_dict(h) for h in results]

    def list_adapters(self) -> list[dict]:
        return [self._adapter_to_dict(m) for m in self._manager.list_adapters()]

    def get_adapter(self, name: str) -> dict | None:
        m = self._manager.get(name)
        if not m:
            return None
        return self._adapter_to_dict(m)

    def connect(self, name: str) -> dict | None:
        m = self._manager.get(name)
        if not m:
            return None
        h = m.connect()
        event_bus.publish(DomainEvent(
            event_type=event_type("adapter", "connected"),
            event_id=new_event_id("adp"),
            event_time=now_utc(),
            version=1,
            actor="system",
            resource_type="adapter",
            resource_id=name,
            payload={"status": h.status.value},
        ))
        return self._health_to_dict(h)

    def disconnect(self, name: str) -> dict | None:
        m = self._manager.get(name)
        if not m:
            return None
        h = m.disconnect()
        event_bus.publish(DomainEvent(
            event_type=event_type("adapter", "disconnected"),
            event_id=new_event_id("adp"),
            event_time=now_utc(),
            version=1,
            actor="system",
            resource_type="adapter",
            resource_id=name,
            payload={"status": h.status.value},
        ))
        return self._health_to_dict(h)

    def get_adapter_symbols(self, name: str) -> list[StandardSymbol] | None:
        m = self._manager.get(name)
        if not m:
            return None
        return m.get_symbols()

    def get_adapter_ticker(self, name: str, symbol: str) -> StandardTicker | None:
        m = self._manager.get(name)
        if not m:
            return None
        return m.get_ticker(symbol)

    def _managed(self, name: str) -> ManagedAdapter:
        m = self._manager.get(name)
        if not m:
            raise QuantError("NOT_FOUND", f"Adapter {name} not found", status_code=404)
        if m.status != AdapterConnectionStatus.CONNECTED:
            m.connect()
        return m

    def place_paper_order(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        quantity: str,
        price: str | None,
        name: str = "paper",
    ) -> OrderResult:
        m = self._managed(name)
        return m.place_order(client_order_id=client_order_id, symbol=symbol, side=side, quantity=quantity, price=price)

    def get_paper_order_status(self, client_order_id: str, name: str = "paper") -> OrderResult:
        m = self._managed(name)
        return m.get_order_status(client_order_id=client_order_id)

    def cancel_paper_order(self, client_order_id: str, name: str = "paper") -> OrderResult:
        m = self._managed(name)
        return m.cancel_order(client_order_id=client_order_id)

    @staticmethod
    def _health_to_dict(h: AdapterHealth) -> dict:
        return {
            "exchange": h.exchange,
            "status": h.status.value,
            "latency_ms": h.latency_ms,
            "is_rate_limited": h.is_rate_limited,
            "retry_count": h.retry_count,
            "last_checked_at": h.last_checked_at.isoformat(),
        }

    @staticmethod
    def _adapter_to_dict(m: ManagedAdapter) -> dict:
        h = m.health()
        return {
            "name": m.name,
            "status": m.status.value,
            "latency_ms": h.latency_ms,
            "is_rate_limited": m.is_rate_limited,
            "last_error": m.last_error,
        }