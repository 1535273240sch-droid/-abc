"""Live exchange adapters: real REST implementations for Binance / OKX / Coinbase.

Each adapter implements the same :class:`ExchangeAdapter` contract as the
paper adapter, plus two live-guard extensions:

- ``get_balance(asset)``   — real available balance (quote asset check)
- ``get_positions()``      — real holdings {symbol: qty} for reconciliation

Design constraints:
- Standard library only (urllib), synchronous — matches the existing
  adapter protocol and ManagedAdapter retry wrapper.
- Credentials are injected as plain dicts; they never appear in logs,
  exceptions carry only HTTP status + exchange error code.
- Testnet support: each adapter takes ``base_url`` so Binance testnet /
  OKX demo / Coinbase sandbox can be used without code changes.
- ``dry_run`` mode signs requests normally but refuses to submit orders
  (returns REJECTED with a clear text) — used by connection tests.
"""

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64decode, b64encode
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.adapters.protocol import (
    AdapterConnectionStatus,
    AdapterHealth,
    AdapterOrderStatus,
    AdapterError,
    ConnectionErrorAdapter,
    ExchangeAdapter,
    OrderResult,
    StandardSymbol,
    StandardTicker,
    utcnow,
)

_JSON_HEADERS = {"Content-Type": "application/json", "User-Agent": "enterprise-ai-quant/0.2"}


class LiveAdapterError(AdapterError):
    """Exchange returned an error or the response could not be parsed."""

    def __init__(self, exchange: str, message: str, http_status: int | None = None, retryable: bool = False):
        super().__init__(f"EXCHANGE_{exchange.upper()}_ERROR" if http_status is None else f"EXCHANGE_HTTP_{http_status}", f"[{exchange}] {message}", retryable=retryable)
        self.http_status = http_status


class _LiveAdapterBase(ExchangeAdapter):
    """Shared plumbing: HTTP, signing hooks, dry-run order guard."""

    exchange_name: str = "live"

    def __init__(
        self,
        credentials: dict[str, str],
        base_url: str,
        dry_run: bool = False,
        timeout: float = 10.0,
    ):
        self._api_key = credentials.get("api_key", "")
        self._api_secret = credentials.get("api_secret", "")
        self._passphrase = credentials.get("passphrase", "")
        self._base_url = base_url.rstrip("/")
        self._dry_run = dry_run
        self._timeout = timeout
        self._status = AdapterConnectionStatus.DISCONNECTED
        self._connected_at: datetime | None = None
        self._last_latency_ms = 0

    # ── lifecycle ────────────────────────────────────────────────────

    def connect(self) -> AdapterHealth:
        started = time.monotonic()
        try:
            # A cheap signed endpoint call validates credentials end-to-end.
            self.get_balance(self._probe_asset())
            self._status = AdapterConnectionStatus.CONNECTED
            self._connected_at = utcnow()
        except AdapterError as exc:
            self._status = AdapterConnectionStatus.FAILED
            raise
        finally:
            self._last_latency_ms = int((time.monotonic() - started) * 1000)
        return self.health()

    def disconnect(self) -> AdapterHealth:
        self._status = AdapterConnectionStatus.DISCONNECTED
        return self.health()

    def health(self) -> AdapterHealth:
        return AdapterHealth(
            exchange=self.exchange_name,
            status=self._status,
            latency_ms=self._last_latency_ms,
            is_rate_limited=False,
            retry_count=0,
        )

    def _probe_asset(self) -> str:
        return "USDT"

    # ── HTTP core ────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        query = urllib.parse.urlencode(params or {})
        headers = dict(_JSON_HEADERS)
        if signed:
            self._sign(headers, method, path, query, body)
        url = f"{self._base_url}{path}"
        if query:
            url = f"{url}?{query}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = self._safe_error_body(exc)
            retryable = exc.code in (418, 429) or exc.code >= 500
            raise LiveAdapterError(self.exchange_name, detail, http_status=exc.code, retryable=retryable) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LiveAdapterError(self.exchange_name, f"network error: {exc}", retryable=True) from exc
        except json.JSONDecodeError as exc:
            raise LiveAdapterError(self.exchange_name, "unparseable JSON response", retryable=True) from exc

    @staticmethod
    def _safe_error_body(exc: urllib.error.HTTPError) -> str:
        """Never leak credentials; keep only status + short exchange message."""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # noqa: BLE001
            body = ""
        return f"HTTP {exc.code}: {body or exc.reason}"

    def _sign(self, headers: dict[str, str], method: str, path: str, query: str, body: dict[str, Any] | None) -> None:
        raise NotImplementedError

    # ── order guard ──────────────────────────────────────────────────

    def _guard_order(self, symbol: str, side: str) -> None:
        if self._status != AdapterConnectionStatus.CONNECTED:
            raise ConnectionErrorAdapter(f"{self.exchange_name} live adapter not connected")
        if self._dry_run:
            raise LiveAdapterError(
                self.exchange_name,
                f"dry-run mode: order submission refused ({side} {symbol})",
            )

    def _require_credentials(self) -> None:
        if not self._api_key or not self._api_secret:
            raise LiveAdapterError(self.exchange_name, "missing api_key/api_secret credentials")


# ════════════════════════════════════════════════════════════════════
# Binance Spot
# ════════════════════════════════════════════════════════════════════


class BinanceLiveAdapter(_LiveAdapterBase):
    """Binance Spot REST (api.binance.com / testnet.binance.vcn)."""

    exchange_name = "binance"

    def _request(self, method, path, params=None, body=None, signed=False):
        # Binance signs the raw query string with everything in it
        # (POST order params go into the query, not the body).
        if signed:
            merged = dict(params or {})
            if body:
                merged.update(body)
                body = None
            query = urllib.parse.urlencode(merged) + f"&timestamp={int(time.time() * 1000)}"
            signature = hmac.new(self._api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
            headers = dict(_JSON_HEADERS)
            headers["X-MBX-APIKEY"] = self._api_key
            url = f"{self._base_url}{path}?{query}&signature={signature}"
            data = None
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            return self._execute(req)
        return super()._request(method, path, params=params, body=body, signed=False)

    def _execute(self, req: urllib.request.Request) -> Any:
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = self._safe_error_body(exc)
            retryable = exc.code in (418, 429) or exc.code >= 500
            raise LiveAdapterError(self.exchange_name, detail, http_status=exc.code, retryable=retryable) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LiveAdapterError(self.exchange_name, f"network error: {exc}", retryable=True) from exc
        except json.JSONDecodeError as exc:
            raise LiveAdapterError(self.exchange_name, "unparseable JSON response", retryable=True) from exc

    # ── market data ──────────────────────────────────────────────────

    def get_symbols(self) -> list[StandardSymbol]:
        data = self._request("GET", "/api/v3/exchangeInfo")
        out = []
        for item in data.get("symbols", [])[:500]:
            out.append(StandardSymbol(
                symbol=item["symbol"],
                base_asset=item.get("baseAsset", ""),
                quote_asset=item.get("quoteAsset", ""),
                market_type="spot",
                status=item.get("status", "TRADING").lower(),
            ))
        return out

    def get_ticker(self, symbol: str) -> StandardTicker:
        data = self._request("GET", "/api/v3/ticker/24hr", params={"symbol": symbol})
        return StandardTicker(
            symbol=symbol,
            source=self.exchange_name,
            last_price=str(data.get("lastPrice", "0")),
            bid_price=str(data.get("bidPrice", "0")),
            ask_price=str(data.get("askPrice", "0")),
            volume_24h=str(data.get("volume", "0")),
            event_time=utcnow(),
            sequence=int(time.time() * 1000),
        )

    # ── account ──────────────────────────────────────────────────────

    def get_balance(self, asset: str = "USDT") -> str:
        data = self._request("GET", "/api/v3/account", signed=True)
        for bal in data.get("balances", []):
            if bal["asset"] == asset:
                return bal["free"]
        return "0"

    def get_positions(self) -> dict[str, str]:
        data = self._request("GET", "/api/v3/account", signed=True)
        return {
            f"{bal['asset']}USDT": bal["free"]
            for bal in data.get("balances", [])
            if Decimal(bal["free"]) > 0 and bal["asset"] not in ("USDT",)
        }

    # ── orders ───────────────────────────────────────────────────────

    def place_order(self, client_order_id: str, symbol: str, side: str, quantity: str, price: str | None) -> OrderResult:
        self._guard_order(symbol, side)
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "quantity": quantity,
            "newClientOrderId": client_order_id,
        }
        if price is not None:
            params["type"] = "LIMIT"
            params["price"] = price
            params["timeInForce"] = "GTC"
        else:
            params["type"] = "MARKET"
        data = self._request("POST", "/api/v3/order", params=params, signed=True)
        return self._to_order_result(data, client_order_id, "placed")

    def cancel_order(self, client_order_id: str) -> OrderResult:
        existing = self._query_order(client_order_id, quiet=True)
        if existing is not None and existing.status is AdapterOrderStatus.FILLED:
            return existing
        data = self._request("DELETE", "/api/v3/order", params={"origClientOrderId": client_order_id}, signed=True)
        return self._to_order_result(data, client_order_id, "cancelled")

    def get_order_status(self, client_order_id: str) -> OrderResult:
        result = self._query_order(client_order_id, quiet=False)
        assert result is not None
        return result

    def _query_order(self, client_order_id: str, quiet: bool) -> OrderResult | None:
        try:
            data = self._request("GET", "/api/v3/order", params={"origClientOrderId": client_order_id}, signed=True)
        except LiveAdapterError as exc:
            if quiet and exc.http_status == 400:
                return None
            raise
        return self._to_order_result(data, client_order_id, "queried")

    @staticmethod
    def _to_order_result(data: dict[str, Any], client_order_id: str, action: str) -> OrderResult:
        status_map = {
            "NEW": AdapterOrderStatus.NEW,
            "PARTIALLY_FILLED": AdapterOrderStatus.PARTIALLY_FILLED,
            "FILLED": AdapterOrderStatus.FILLED,
            "CANCELED": AdapterOrderStatus.CANCELLED,
            "REJECTED": AdapterOrderStatus.REJECTED,
            "EXPIRED": AdapterOrderStatus.CANCELLED,
        }
        executed = str(data.get("executedQty", "0"))
        avg = None
        if Decimal(executed) > 0 and data.get("cummulativeQuoteQty"):
            avg = str((Decimal(str(data["cummulativeQuoteQty"])) / Decimal(executed)).quantize(Decimal("0.01")))
        return OrderResult(
            client_order_id=client_order_id,
            exchange="binance",
            status=status_map.get(data.get("status", "NEW"), AdapterOrderStatus.NEW),
            filled_quantity=executed,
            average_price=avg,
            text=f"binance order {action}",
        )


# ════════════════════════════════════════════════════════════════════
# OKX v5
# ════════════════════════════════════════════════════════════════════


class OkxLiveAdapter(_LiveAdapterBase):
    """OKX v5 REST (www.okx.com / demo trading host)."""

    exchange_name = "okx"

    def _sign(self, headers, method, path, query, body):
        self._require_credentials()
        if not self._passphrase:
            raise LiveAdapterError(self.exchange_name, "missing passphrase credential")
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        prehash = f"{timestamp}{method.upper()}{path}" + (f"?{query}" if query else "")
        if body is not None:
            prehash += json.dumps(body, separators=(",", ":"))
        signature = b64encode(hmac.new(self._api_secret.encode(), prehash.encode(), hashlib.sha256).digest()).decode()
        headers.update({
            "OK-ACCESS-KEY": self._api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self._passphrase,
        })

    # ── market data (public, unsigned) ───────────────────────────────

    def get_symbols(self) -> list[StandardSymbol]:
        data = self._request("GET", "/api/v5/public/instruments", params={"instType": "SPOT"})
        out = []
        for item in data.get("data", [])[:500]:
            out.append(StandardSymbol(
                symbol=item["instId"],
                base_asset=item.get("baseCc", ""),
                quote_asset=item.get("quoteCc", ""),
                market_type="spot",
                status="trading" if item.get("state") == "live" else item.get("state", "unknown"),
            ))
        return out

    def get_ticker(self, symbol: str) -> StandardTicker:
        data = self._request("GET", "/api/v5/market/ticker", params={"instId": symbol})
        row = (data.get("data") or [{}])[0]
        return StandardTicker(
            symbol=symbol,
            source=self.exchange_name,
            last_price=row.get("last", "0"),
            bid_price=row.get("bidPx", "0"),
            ask_price=row.get("askPx", "0"),
            volume_24h=row.get("vol24h", "0"),
            event_time=utcnow(),
            sequence=int(row.get("ts", time.time() * 1000)),
        )

    # ── account ──────────────────────────────────────────────────────

    def get_balance(self, asset: str = "USDT") -> str:
        data = self._request("GET", "/api/v5/account/balance", signed=True)
        for detail in (data.get("data") or [{}])[0].get("details", []):
            if detail.get("ccy") == asset:
                return detail.get("availBal", "0")
        return "0"

    def get_positions(self) -> dict[str, str]:
        data = self._request("GET", "/api/v5/account/balance", signed=True)
        out = {}
        for detail in (data.get("data") or [{}])[0].get("details", []):
            ccy, avail = detail.get("ccy", ""), detail.get("availBal", "0")
            if ccy and ccy != "USDT" and Decimal(avail) > 0:
                out[f"{ccy}-USDT"] = avail
        return out

    # ── orders ───────────────────────────────────────────────────────

    def place_order(self, client_order_id: str, symbol: str, side: str, quantity: str, price: str | None) -> OrderResult:
        self._guard_order(symbol, side)
        body: dict[str, Any] = {
            "instId": symbol,
            "side": side.lower(),
            "sz": quantity,
            "clOrdId": client_order_id[:32],
            "tdMode": "cash",
        }
        body["ordType"] = "limit" if price is not None else "market"
        if price is not None:
            body["px"] = price
        data = self._request("POST", "/api/v5/trade/order", body=body, signed=True)
        row = (data.get("data") or [{}])[0]
        if row.get("sCode") not in ("0", 0):
            raise LiveAdapterError(self.exchange_name, f"order rejected: {row.get('sMsg', 'unknown')}")
        return OrderResult(
            client_order_id=client_order_id,
            exchange=self.exchange_name,
            status=AdapterOrderStatus.NEW,
            filled_quantity="0",
            average_price=None,
            text=f"okx order accepted: {row.get('ordId', '')}",
        )

    def cancel_order(self, client_order_id: str) -> OrderResult:
        try:
            self._request("POST", "/api/v5/trade/cancel-order", body={"clOrdId": client_order_id[:32]}, signed=True)
        except LiveAdapterError:
            pass  # already filled/cancelled — fall through to status query
        return self.get_order_status(client_order_id)

    def get_order_status(self, client_order_id: str) -> OrderResult:
        data = self._request("GET", "/api/v5/trade/order", params={"clOrdId": client_order_id[:32]}, signed=True)
        row = (data.get("data") or [{}])[0]
        status_map = {
            "live": AdapterOrderStatus.NEW,
            "partially_filled": AdapterOrderStatus.PARTIALLY_FILLED,
            "filled": AdapterOrderStatus.FILLED,
            "canceled": AdapterOrderStatus.CANCELLED,
            "cancelled": AdapterOrderStatus.CANCELLED,
        }
        avg = row.get("avgPx") or None
        return OrderResult(
            client_order_id=client_order_id,
            exchange=self.exchange_name,
            status=status_map.get(row.get("state", "live"), AdapterOrderStatus.NEW),
            filled_quantity=str(row.get("accFillSz", "0")),
            average_price=avg,
            text=f"okx order state: {row.get('state', '')}",
        )


# ════════════════════════════════════════════════════════════════════
# Coinbase Exchange (HMAC API)
# ════════════════════════════════════════════════════════════════════


class CoinbaseLiveAdapter(_LiveAdapterBase):
    """Coinbase Exchange REST (api.exchange.coinbase.com / sandbox)."""

    exchange_name = "coinbase"

    def _coinbase_symbol(self, symbol: str) -> str:
        # BTCUSDT → BTC-USD (quote strip); BTC-USD passes through.
        if "-" in symbol:
            return symbol
        for quote in ("USDT", "USD", "USDC"):
            if symbol.endswith(quote) and len(symbol) > len(quote):
                return f"{symbol[: -len(quote)]}-USD"
        return symbol

    def _sign(self, headers, method, path, query, body):
        self._require_credentials()
        timestamp = str(time.time())
        message = timestamp + method.upper() + path + (f"?{query}" if query else "")
        if body is not None:
            message += json.dumps(body, separators=(",", ":"))
        signature = b64encode(
            hmac.new(b64decode(self._api_secret), message.encode(), hashlib.sha256).digest()
        ).decode()
        headers.update({
            "CB-ACCESS-KEY": self._api_key,
            "CB-ACCESS-SIGN": signature,
            "CB-ACCESS-TIMESTAMP": timestamp,
            "CB-ACCESS-PASSPHRASE": self._passphrase,
        })

    # ── market data ──────────────────────────────────────────────────

    def get_symbols(self) -> list[StandardSymbol]:
        data = self._request("GET", "/products")
        out = []
        for item in data[:500]:
            base, _, quote = item["id"].partition("-")
            out.append(StandardSymbol(
                symbol=item["id"],
                base_asset=base,
                quote_asset=quote or "USD",
                market_type="spot",
                status="trading" if item.get("trading_disabled") is False else "unknown",
            ))
        return out

    def get_ticker(self, symbol: str) -> StandardTicker:
        product = self._coinbase_symbol(symbol)
        data = self._request("GET", f"/products/{product}/ticker")
        return StandardTicker(
            symbol=symbol,
            source=self.exchange_name,
            last_price=str(data.get("price", "0")),
            bid_price=str(data.get("bid", "0")),
            ask_price=str(data.get("ask", "0")),
            volume_24h=str(data.get("volume", "0")),
            event_time=utcnow(),
            sequence=int(time.time() * 1000),
        )

    # ── account ──────────────────────────────────────────────────────

    def get_balance(self, asset: str = "USD") -> str:
        data = self._request("GET", "/accounts", signed=True)
        for acc in data:
            if acc.get("currency") == asset:
                return acc.get("available", "0")
        return "0"

    def get_positions(self) -> dict[str, str]:
        data = self._request("GET", "/accounts", signed=True)
        return {
            f"{acc['currency']}-USD": acc.get("available", "0")
            for acc in data
            if Decimal(acc.get("available", "0")) > 0 and acc.get("currency") not in ("USD", "USDT", "USDC")
        }

    def _probe_asset(self) -> str:
        return "USD"

    # ── orders ───────────────────────────────────────────────────────

    def place_order(self, client_order_id: str, symbol: str, side: str, quantity: str, price: str | None) -> OrderResult:
        self._guard_order(symbol, side)
        body: dict[str, Any] = {
            "product_id": self._coinbase_symbol(symbol),
            "side": side.lower(),
            "size": quantity,
            "client_oid": client_order_id,
            "type": "limit" if price is not None else "market",
        }
        if price is not None:
            body["price"] = price
            body["post_only"] = False
        data = self._request("POST", "/orders", body=body, signed=True)
        status = AdapterOrderStatus.NEW
        if data.get("status") == "done" and data.get("filled_size") not in (None, "", "0"):
            status = AdapterOrderStatus.FILLED
        elif data.get("filled_size") not in (None, "", "0"):
            status = AdapterOrderStatus.PARTIALLY_FILLED
        elif data.get("status") in ("rejected", "done"):
            status = AdapterOrderStatus.REJECTED
        return OrderResult(
            client_order_id=client_order_id,
            exchange=self.exchange_name,
            status=status,
            filled_quantity=str(data.get("filled_size", "0")),
            average_price=data.get("executed_value") and str(
                (Decimal(str(data["executed_value"])) / Decimal(str(data["filled_size"]))).quantize(Decimal("0.01"))
            ) if data.get("filled_size") not in (None, "", "0") and Decimal(str(data.get("filled_size", "0"))) > 0 else None,
            text=f"coinbase order id {data.get('id', '')}",
        )

    def cancel_order(self, client_order_id: str) -> OrderResult:
        try:
            self._request("DELETE", "/orders/client:" + client_order_id, signed=True)
        except LiveAdapterError:
            pass
        return self.get_order_status(client_order_id)

    def get_order_status(self, client_order_id: str) -> OrderResult:
        try:
            data = self._request("GET", f"/orders/client:{client_order_id}", signed=True)
        except LiveAdapterError as exc:
            if exc.http_status == 404:
                return OrderResult(
                    client_order_id=client_order_id,
                    exchange=self.exchange_name,
                    status=AdapterOrderStatus.REJECTED,
                    filled_quantity="0",
                    average_price=None,
                    text="order not found on coinbase",
                )
            raise
        status_map = {
            "pending": AdapterOrderStatus.NEW,
            "open": AdapterOrderStatus.NEW,
            "active": AdapterOrderStatus.NEW,
            "done": AdapterOrderStatus.FILLED,
        }
        filled = str(data.get("filled_size", "0"))
        status = status_map.get(data.get("status", "open"), AdapterOrderStatus.NEW)
        if status is AdapterOrderStatus.FILLED and data.get("settle") is False:
            status = AdapterOrderStatus.PARTIALLY_FILLED if Decimal(filled) > 0 else AdapterOrderStatus.NEW
        avg = None
        if Decimal(filled) > 0 and data.get("executed_value"):
            avg = str((Decimal(str(data["executed_value"])) / Decimal(filled)).quantize(Decimal("0.01")))
        return OrderResult(
            client_order_id=client_order_id,
            exchange=self.exchange_name,
            status=status,
            filled_quantity=filled,
            average_price=avg,
            text=f"coinbase order status: {data.get('status', '')}",
        )


# ════════════════════════════════════════════════════════════════════
# Factory
# ════════════════════════════════════════════════════════════════════

DEFAULT_LIVE_URLS: dict[str, str] = {
    "binance": "https://api.binance.com",
    "binance-testnet": "https://testnet.binance.vision",
    "okx": "https://www.okx.com",
    "okx-demo": "https://www.okx.com",
    "coinbase": "https://api.exchange.coinbase.com",
    "coinbase-sandbox": "https://api.exchange.coinbase.com",
}

ADAPTER_CLASSES: dict[str, type[_LiveAdapterBase]] = {
    "binance": BinanceLiveAdapter,
    "okx": OkxLiveAdapter,
    "coinbase": CoinbaseLiveAdapter,
}


def build_live_adapter(exchange: str, credentials: dict[str, str], base_url: str | None = None, dry_run: bool = False) -> _LiveAdapterBase:
    """Create a live adapter by exchange name with sane URL defaults."""
    key = exchange.lower().strip()
    cls = ADAPTER_CLASSES.get(key)
    if cls is None:
        raise LiveAdapterError(exchange, f"no live adapter implemented for exchange '{exchange}'")
    url = base_url or DEFAULT_LIVE_URLS.get(key)
    if url is None:
        raise LiveAdapterError(exchange, f"no default URL for exchange '{exchange}'")
    return cls(credentials, url, dry_run=dry_run)
