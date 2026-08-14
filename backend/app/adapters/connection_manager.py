"""Adapter connection registry and lifecycle management."""

import threading
import time
from typing import Any

from app.adapters.protocol import (
    AdapterConnectionStatus,
    AdapterHealth,
    AdapterError,
    ConnectionErrorAdapter,
    ExchangeAdapter,
    RateLimitError,
    RetryExhaustedError,
    utcnow,
)
from app.adapters.rate_limiter import RateLimiter


class ManagedAdapter:
    """Wraps an ExchangeAdapter with connection state, rate limiter, and retry logic."""

    def __init__(
        self,
        name: str,
        adapter: ExchangeAdapter,
        max_requests_per_second: float = 10.0,
        max_retries: int = 3,
    ):
        self.name = name
        self._adapter = adapter
        self._status = AdapterConnectionStatus.DISCONNECTED
        self._rate_limiter = RateLimiter(max_requests_per_second)
        self._max_retries = max_retries
        self._latency_ms = 15
        self._lock = threading.Lock()
        self._last_error: str | None = None

    def connect(self) -> AdapterHealth:
        with self._lock:
            self._status = AdapterConnectionStatus.CONNECTING
            self._last_error = None
            # Simulate connection latency
            self._latency_ms = 42 if self.name in ("binance",) else 58
            self._status = AdapterConnectionStatus.CONNECTED
            return self._build_health()

    def disconnect(self) -> AdapterHealth:
        with self._lock:
            self._status = AdapterConnectionStatus.DISCONNECTED
            self._last_error = None
            return self._build_health()

    def health(self) -> AdapterHealth:
        with self._lock:
            if self._status == AdapterConnectionStatus.CONNECTED:
                self._latency_ms = max(5, self._latency_ms + (-5 if self._latency_ms > 20 else 3))
            return self._build_health()

    def execute(self, action: str, **kwargs: Any) -> Any:
        if self._status != AdapterConnectionStatus.CONNECTED:
            raise ConnectionErrorAdapter(f"Adapter {self.name} is {self._status.value}")

        if not self._rate_limiter.acquire(timeout=0.1):
            raise RateLimitError(f"Adapter {self.name} rate limited")

        retries = 0
        while retries <= self._max_retries:
            try:
                method = getattr(self._adapter, action, None)
                if not method:
                    raise ValueError(f"Unknown adapter action: {action}")
                result = method(**kwargs)
                self._latency_ms = max(5, self._latency_ms - 2)
                self._last_error = None
                return result
            except AdapterError as e:
                if not e.retryable or retries >= self._max_retries:
                    self._last_error = e.message
                    raise
                retries += 1
                time.sleep(0.05 * retries)
            except Exception as e:
                self._last_error = str(e)
                raise

        raise RetryExhaustedError(f"Adapter {self.name} retries exhausted for {action}")

    def get_symbols(self) -> list:
        return self.execute("get_symbols")

    def get_ticker(self, symbol: str) -> Any:
        return self.execute("get_ticker", symbol=symbol)

    def place_order(self, client_order_id: str, symbol: str, side: str, quantity: str, price: str | None) -> Any:
        return self.execute("place_order", client_order_id=client_order_id, symbol=symbol, side=side, quantity=quantity, price=price)

    def cancel_order(self, client_order_id: str) -> Any:
        return self.execute("cancel_order", client_order_id=client_order_id)

    def get_order_status(self, client_order_id: str) -> Any:
        return self.execute("get_order_status", client_order_id=client_order_id)

    @property
    def is_rate_limited(self) -> bool:
        return self._rate_limiter.is_rate_limited

    @property
    def status(self) -> AdapterConnectionStatus:
        return self._status

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _build_health(self) -> AdapterHealth:
        return AdapterHealth(
            exchange=self.name,
            status=self._status,
            latency_ms=self._latency_ms,
            is_rate_limited=self._rate_limiter.is_rate_limited,
            retry_count=self._max_retries,
        )


class ConnectionManager:
    """Registry of all managed adapters."""

    def __init__(self):
        self._adapters: dict[str, ManagedAdapter] = {}
        self._lock = threading.Lock()

    def register(self, name: str, adapter: ExchangeAdapter, max_rps: float = 10.0, max_retries: int = 3) -> ManagedAdapter:
        with self._lock:
            managed = ManagedAdapter(name, adapter, max_rps, max_retries)
            self._adapters[name] = managed
            return managed

    def get(self, name: str) -> ManagedAdapter | None:
        return self._adapters.get(name)

    def list_adapters(self) -> list[ManagedAdapter]:
        return [m for m in self._adapters.values()]

    def connect_all(self) -> list[AdapterHealth]:
        return [m.connect() for m in self._adapters.values()]

    def disconnect_all(self) -> list[AdapterHealth]:
        return [m.disconnect() for m in self._adapters.values()]