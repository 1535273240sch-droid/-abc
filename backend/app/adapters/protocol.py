"""Stable adapter protocol / typed contracts.

Defines the boundary between the trading core and external market adapters.
Adapters must NEVER leak exchange-private models to upper layers. All outputs
are standardized, Decimal/string typed contracts (ARCHITECTURE.md section 3:
adapters "不向上层暴露交易所私有模型").
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AdapterConnectionStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    FAILED = "failed"


class AdapterOrderStatus(str, Enum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AdapterHealth:
    exchange: str
    status: AdapterConnectionStatus
    latency_ms: int
    is_rate_limited: bool
    retry_count: int
    last_checked_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True)
class StandardTicker:
    symbol: str
    source: str
    last_price: str
    bid_price: str
    ask_price: str
    volume_24h: str
    event_time: datetime
    sequence: int


@dataclass(frozen=True)
class StandardSymbol:
    symbol: str
    base_asset: str
    quote_asset: str
    market_type: str
    status: str


@dataclass(frozen=True)
class OrderResult:
    client_order_id: str
    exchange: str
    status: AdapterOrderStatus
    filled_quantity: str
    average_price: str | None
    text: str
    created_at: datetime = field(default_factory=utcnow)


class ExchangeAdapter(ABC):
    """Abstract adapter contract. Implementations must be deterministic in paper mode."""

    @abstractmethod
    def connect(self) -> AdapterHealth:
        ...

    @abstractmethod
    def disconnect(self) -> AdapterHealth:
        ...

    @abstractmethod
    def health(self) -> AdapterHealth:
        ...

    @abstractmethod
    def get_symbols(self) -> list[StandardSymbol]:
        ...

    @abstractmethod
    def get_ticker(self, symbol: str) -> StandardTicker:
        ...

    @abstractmethod
    def place_order(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        quantity: str,
        price: str | None,
    ) -> OrderResult:
        ...

    @abstractmethod
    def cancel_order(self, client_order_id: str) -> OrderResult:
        ...

    @abstractmethod
    def get_order_status(self, client_order_id: str) -> OrderResult:
        ...


class AdapterError(Exception):
    """Raised for adapter-level errors (rate limit, connection, retry exhausted)."""

    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class RateLimitError(AdapterError):
    def __init__(self, message: str = "Adapter rate limit exceeded"):
        super().__init__("ADAPTER_RATE_LIMITED", message, retryable=True)


class ConnectionErrorAdapter(AdapterError):
    def __init__(self, message: str = "Adapter not connected"):
        super().__init__("ADAPTER_NOT_CONNECTED", message, retryable=True)


class RetryExhaustedError(AdapterError):
    def __init__(self, message: str = "Adapter retry attempts exhausted"):
        super().__init__("ADAPTER_RETRY_EXHAUSTED", message, retryable=False)