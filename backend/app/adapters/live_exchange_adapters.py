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
        super().__init__(
            f"EXCHANGE_{exchange.upper()}_ERROR" if http_status is None else f"EXCHANGE_HTTP_{http_status}",
            f"[{exchange}] {message}",
            retryable=retryable,
        )
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
        except AdapterError:
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
        headers: dict[str, str] | None = None,
    ) -> Any:
        query = urllib.parse.urlencode(params or {})
        req_headers = dict(_JSON_HEADERS)
        if headers:
            req_headers.update(headers)
        if signed:
            self._sign(req_headers, method, path, query, body)
        url = f"{self._base_url}{path}" + (f"?{query}" if query else "")
        data = None
        if body is not None:
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
        return self._execute(req)

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

    @staticmethod
    def _safe_error_body(exc: urllib.error.HTTPError) -> str:
        """Never leak credentials; keep only status + short exchange message."""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:300]
            for pattern in [r"(signature=)[^&]+", r"(apiKey=)[^&]+", r"(secret=)[^&]+", r"(passphrase=)[^&]+"]:
                body = re.sub(pattern, r"\1***REDACTED***", body, flags=re.IGNORECASE)
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
# Binance Spot & USD-M Futures
# ════════════════════════════════════════════════════════════════════


class BinanceLiveAdapter(_LiveAdapterBase):
    """Binance Spot & USD-M Futures REST (api.binance.com / fapi.binance.com)."""

    exchange_name = "binance"

    def sign(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        timestamp: int | None = None,
        recv_window: int = 5000,
    ) -> dict[str, Any]:
        """Construct HMAC-SHA256 signature, headers and full query string."""
        self._require_credentials()
        merged = dict(params or {})
        if body:
            merged.update(body)
        if "timestamp" not in merged:
            merged["timestamp"] = timestamp if timestamp is not None else int(time.time() * 1000)
        if "recvWindow" not in merged and recv_window:
            merged["recvWindow"] = recv_window
        query = urllib.parse.urlencode(merged)
        signature = hmac.new(self._api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        headers = dict(_JSON_HEADERS)
        headers["X-MBX-APIKEY"] = self._api_key
        full_query = f"{query}&signature={signature}"
        full_url = f"{self._base_url}{path}?{full_query}"
        return {
            "headers": headers,
            "query": full_query,
            "signature": signature,
            "url": full_url,
            "params": {**merged, "signature": signature},
        }

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        signed: bool = False,
        headers: dict[str, str] | None = None,
    ) -> Any:
        if signed:
            sign_res = self.sign(method, path, params=params, body=body)
            req_headers = sign_res["headers"]
            if headers:
                req_headers.update(headers)
            url = sign_res["url"]
            req = urllib.request.Request(url, data=None, headers=req_headers, method=method.upper())
            return self._execute(req)
        return super()._request(method, path, params=params, body=body, signed=False, headers=headers)

    # ── market data ──────────────────────────────────────────────────

    def get_symbols(self, is_contract: bool = False) -> list[StandardSymbol]:
        path = "/fapi/v1/exchangeInfo" if is_contract else "/api/v3/exchangeInfo"
        data = self._request("GET", path)
        out = []
        for item in data.get("symbols", [])[:500]:
            out.append(StandardSymbol(
                symbol=item["symbol"],
                base_asset=item.get("baseAsset", ""),
                quote_asset=item.get("quoteAsset", ""),
                market_type="future" if is_contract else "spot",
                status=item.get("status", "TRADING").lower(),
            ))
        return out

    def get_ticker(self, symbol: str, is_contract: bool = False) -> StandardTicker:
        path = "/fapi/v1/ticker/24hr" if is_contract else "/api/v3/ticker/24hr"
        data = self._request("GET", path, params={"symbol": symbol})
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

    # ── account & positions ──────────────────────────────────────────

    def get_balance(self, asset: str = "USDT", is_contract: bool = False) -> str:
        if is_contract:
            data = self._request("GET", "/fapi/v2/balance", signed=True)
            for bal in data:
                if bal.get("asset") == asset:
                    return str(bal.get("availableBalance", bal.get("balance", "0")))
            return "0"
        data = self._request("GET", "/api/v3/account", signed=True)
        for bal in data.get("balances", []):
            if bal["asset"] == asset:
                return str(bal.get("free", "0"))
        return "0"

    def get_positions(self, is_contract: bool = False) -> dict[str, str]:
        if is_contract:
            data = self._request("GET", "/fapi/v2/positionRisk", signed=True)
            out = {}
            for item in data:
                pos_amt = item.get("positionAmt", "0")
                if Decimal(str(pos_amt)) != 0:
                    out[item["symbol"]] = str(pos_amt)
            return out
        data = self._request("GET", "/api/v3/account", signed=True)
        return {
            f"{bal['asset']}USDT": str(bal.get("free", "0"))
            for bal in data.get("balances", [])
            if Decimal(str(bal.get("free", "0"))) > 0 and bal["asset"] not in ("USDT",)
        }

    def get_account_balance(self, is_contract: bool = False) -> dict[str, Any]:
        if is_contract:
            data = self._request("GET", "/fapi/v2/account", signed=True)
            return {
                "total_equity": str(data.get("totalWalletBalance", "0")),
                "available_balance": str(data.get("availableBalance", "0")),
                "unrealized_pnl": str(data.get("totalUnrealizedProfit", "0")),
                "positions": data.get("positions", []),
                "assets": data.get("assets", []),
            }
        data = self._request("GET", "/api/v3/account", signed=True)
        return {
            "account_type": data.get("accountType", "SPOT"),
            "can_trade": data.get("canTrade", True),
            "balances": {
                b["asset"]: {"free": b["free"], "locked": b["locked"]}
                for b in data.get("balances", [])
                if Decimal(b["free"]) > 0 or Decimal(b["locked"]) > 0
            },
        }

    # ── orders ───────────────────────────────────────────────────────

    def place_order(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        quantity: str,
        price: str | None = None,
        is_contract: bool = False,
        order_type: str | None = None,
        time_in_force: str = "GTC",
    ) -> OrderResult:
        self._guard_order(symbol, side)
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "quantity": quantity,
            "newClientOrderId": client_order_id,
        }
        if price is not None:
            params["type"] = order_type or "LIMIT"
            params["price"] = price
            params["timeInForce"] = time_in_force
        else:
            params["type"] = order_type or "MARKET"
        path = "/fapi/v1/order" if is_contract else "/api/v3/order"
        data = self._request("POST", path, params=params, signed=True)
        return self._to_order_result(data, client_order_id, "placed", is_contract=is_contract)

    def cancel_order(self, client_order_id: str, symbol: str | None = None, is_contract: bool = False) -> OrderResult:
        existing = self._query_order(client_order_id, symbol=symbol, is_contract=is_contract, quiet=True)
        if existing is not None and existing.status is AdapterOrderStatus.FILLED:
            return existing
        params: dict[str, Any] = {"origClientOrderId": client_order_id}
        if symbol:
            params["symbol"] = symbol
        path = "/fapi/v1/order" if is_contract else "/api/v3/order"
        data = self._request("DELETE", path, params=params, signed=True)
        return self._to_order_result(data, client_order_id, "cancelled", is_contract=is_contract)

    def get_order_status(self, client_order_id: str, symbol: str | None = None, is_contract: bool = False) -> OrderResult:
        result = self._query_order(client_order_id, symbol=symbol, is_contract=is_contract, quiet=False)
        assert result is not None
        return result

    def _query_order(self, client_order_id: str, symbol: str | None = None, is_contract: bool = False, quiet: bool = False) -> OrderResult | None:
        params: dict[str, Any] = {"origClientOrderId": client_order_id}
        if symbol:
            params["symbol"] = symbol
        path = "/fapi/v1/order" if is_contract else "/api/v3/order"
        try:
            data = self._request("GET", path, params=params, signed=True)
        except LiveAdapterError as exc:
            if quiet and exc.http_status in (400, 404):
                return None
            raise
        return self._to_order_result(data, client_order_id, "queried", is_contract=is_contract)

    @staticmethod
    def _to_order_result(data: dict[str, Any], client_order_id: str, action: str, is_contract: bool = False) -> OrderResult:
        status_map = {
            "NEW": AdapterOrderStatus.NEW,
            "PARTIALLY_FILLED": AdapterOrderStatus.PARTIALLY_FILLED,
            "FILLED": AdapterOrderStatus.FILLED,
            "CANCELED": AdapterOrderStatus.CANCELLED,
            "PENDING_CANCEL": AdapterOrderStatus.NEW,
            "REJECTED": AdapterOrderStatus.REJECTED,
            "EXPIRED": AdapterOrderStatus.REJECTED,
        }
        executed = str(data.get("executedQty", "0"))
        avg = None
        if data.get("avgPrice") and Decimal(str(data["avgPrice"])) > 0:
            avg = str(data["avgPrice"])
        elif Decimal(executed) > 0 and data.get("cummulativeQuoteQty"):
            avg = str((Decimal(str(data["cummulativeQuoteQty"])) / Decimal(executed)).quantize(Decimal("0.01")))
        return OrderResult(
            client_order_id=client_order_id,
            exchange="binance",
            status=status_map.get(data.get("status", "NEW"), AdapterOrderStatus.NEW),
            filled_quantity=executed,
            average_price=avg,
            text=f"binance {'futures ' if is_contract else ''}order {action}",
        )

    # ── User Data Stream (listenKey) ─────────────────────────────────

    def create_listen_key(self, is_contract: bool = False) -> str:
        self._require_credentials()
        path = "/fapi/v1/listenKey" if is_contract else "/api/v3/userDataStream"
        headers = {"X-MBX-APIKEY": self._api_key}
        data = self._request("POST", path, signed=False, headers=headers)
        return str(data.get("listenKey", ""))

    def keepalive_listen_key(self, listen_key: str, is_contract: bool = False) -> bool:
        self._require_credentials()
        path = "/fapi/v1/listenKey" if is_contract else "/api/v3/userDataStream"
        headers = {"X-MBX-APIKEY": self._api_key}
        params = {"listenKey": listen_key} if not is_contract else {}
        self._request("PUT", path, params=params, signed=False, headers=headers)
        return True

    def close_listen_key(self, listen_key: str, is_contract: bool = False) -> bool:
        self._require_credentials()
        path = "/fapi/v1/listenKey" if is_contract else "/api/v3/userDataStream"
        headers = {"X-MBX-APIKEY": self._api_key}
        params = {"listenKey": listen_key} if not is_contract else {}
        self._request("DELETE", path, params=params, signed=False, headers=headers)
        return True


# ════════════════════════════════════════════════════════════════════
# OKX v5
# ════════════════════════════════════════════════════════════════════


class OkxLiveAdapter(_LiveAdapterBase):
    """OKX v5 REST (www.okx.com / demo trading host)."""

    exchange_name = "okx"

    def __init__(self, credentials: dict[str, str], base_url: str, dry_run: bool = False, timeout: float = 10.0, is_demo: bool = False):
        super().__init__(credentials, base_url, dry_run=dry_run, timeout=timeout)
        self._is_demo = is_demo or ("demo" in base_url.lower()) or ("testnet" in base_url.lower())

    def sign(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> dict[str, str]:
        """Construct ISO 8601 UTC timestamp + Prehash HMAC-SHA256 Base64 signature and headers."""
        self._require_credentials()
        if not self._passphrase:
            raise LiveAdapterError(self.exchange_name, "missing passphrase credential")
        ts = timestamp or (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z")
        query_str = urllib.parse.urlencode(params or {}) if params else ""
        request_path = path + (f"?{query_str}" if query_str else "")
        body_str = ""
        if body is not None:
            body_str = json.dumps(body, separators=(",", ":"))
        prehash = f"{ts}{method.upper()}{request_path}{body_str}"
        signature = b64encode(hmac.new(self._api_secret.encode("utf-8"), prehash.encode("utf-8"), hashlib.sha256).digest()).decode("utf-8")
        headers = dict(_JSON_HEADERS)
        headers.update({
            "OK-ACCESS-KEY": self._api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self._passphrase,
        })
        if getattr(self, "_is_demo", False):
            headers["x-simulated-trading"] = "1"
        return headers

    def _sign(self, headers: dict[str, str], method: str, path: str, query: str, body: dict[str, Any] | None) -> None:
        params_dict = dict(urllib.parse.parse_qsl(query)) if query else None
        signed_headers = self.sign(method, path, params=params_dict, body=body)
        headers.update(signed_headers)

    def get_ws_auth_params(self, timestamp: str | None = None) -> dict[str, str]:
        """Generate WebSocket login authentication arguments."""
        self._require_credentials()
        if not self._passphrase:
            raise LiveAdapterError(self.exchange_name, "missing passphrase credential")
        ts = timestamp or str(round(time.time(), 3))
        prehash = f"{ts}GET/users/self/verify"
        sign = b64encode(hmac.new(self._api_secret.encode("utf-8"), prehash.encode("utf-8"), hashlib.sha256).digest()).decode("utf-8")
        return {
            "apiKey": self._api_key,
            "passphrase": self._passphrase,
            "timestamp": ts,
            "sign": sign,
        }

    # ── market data (public, unsigned) ───────────────────────────────

    def get_symbols(self, inst_type: str = "SPOT") -> list[StandardSymbol]:
        data = self._request("GET", "/api/v5/public/instruments", params={"instType": inst_type.upper()})
        out = []
        for item in data.get("data", [])[:500]:
            out.append(StandardSymbol(
                symbol=item["instId"],
                base_asset=item.get("baseCc", item.get("ctValCcy", "")),
                quote_asset=item.get("quoteCc", item.get("settleCcy", "")),
                market_type="spot" if inst_type.upper() == "SPOT" else "perpetual",
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

    # ── account & positions ──────────────────────────────────────────

    def get_balance(self, asset: str = "USDT") -> str:
        data = self._request("GET", "/api/v5/account/balance", signed=True)
        for detail in (data.get("data") or [{}])[0].get("details", []):
            if detail.get("ccy") == asset:
                return str(detail.get("availBal", "0"))
        return "0"

    def get_positions(self, inst_type: str | None = None) -> dict[str, str]:
        if inst_type in ("SWAP", "FUTURES", "MARGIN"):
            data = self._request("GET", "/api/v5/account/positions", params={"instType": inst_type}, signed=True)
            out = {}
            for pos in data.get("data", []):
                pos_val = pos.get("pos", "0")
                if Decimal(str(pos_val)) != 0:
                    out[pos["instId"]] = str(pos_val)
            return out
        data = self._request("GET", "/api/v5/account/balance", signed=True)
        out = {}
        for detail in (data.get("data") or [{}])[0].get("details", []):
            ccy, avail = detail.get("ccy", ""), detail.get("availBal", "0")
            if ccy and ccy != "USDT" and Decimal(str(avail)) > 0:
                out[f"{ccy}-USDT"] = str(avail)
        return out

    def get_account_balance(self) -> dict[str, Any]:
        data = self._request("GET", "/api/v5/account/balance", signed=True)
        row = (data.get("data") or [{}])[0]
        return {
            "total_equity": str(row.get("totalEq", "0")),
            "adjusted_equity": str(row.get("adjEq", "0")),
            "details": row.get("details", []),
        }

    # ── orders ───────────────────────────────────────────────────────

    def place_order(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        quantity: str,
        price: str | None = None,
        is_contract: bool = False,
        pos_side: str = "net",
        td_mode: str | None = None,
        order_type: str | None = None,
    ) -> OrderResult:
        self._guard_order(symbol, side)
        resolved_td_mode = td_mode or ("cross" if is_contract or "-SWAP" in symbol else "cash")
        body: dict[str, Any] = {
            "instId": symbol,
            "side": side.lower(),
            "sz": quantity,
            "clOrdId": client_order_id[:32],
            "tdMode": resolved_td_mode,
            "ordType": (order_type or ("limit" if price is not None else "market")).lower(),
        }
        if is_contract or "-SWAP" in symbol:
            body["posSide"] = pos_side
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

    def cancel_order(self, client_order_id: str, symbol: str | None = None) -> OrderResult:
        body: dict[str, Any] = {"clOrdId": client_order_id[:32]}
        if symbol:
            body["instId"] = symbol
        try:
            self._request("POST", "/api/v5/trade/cancel-order", body=body, signed=True)
        except LiveAdapterError:
            pass  # already filled/cancelled — fall through to status query
        return self.get_order_status(client_order_id, symbol=symbol)

    def get_order_status(self, client_order_id: str, symbol: str | None = None) -> OrderResult:
        params: dict[str, Any] = {"clOrdId": client_order_id[:32]}
        if symbol:
            params["instId"] = symbol
        data = self._request("GET", "/api/v5/trade/order", params=params, signed=True)
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
            ask_price=str(data.get("askPrice", "0")),
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
    "binance-futures": "https://fapi.binance.com",
    "binance-futures-testnet": "https://testnet.binancefuture.com",
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


def build_live_adapter(exchange: str, credentials: dict[str, str], base_url: str | None = None, dry_run: bool = False, is_demo: bool = False) -> _LiveAdapterBase:
    """Create a live adapter by exchange name with sane URL defaults."""
    key = exchange.lower().strip()
    cls = ADAPTER_CLASSES.get(key)
    if cls is None:
        raise LiveAdapterError(exchange, f"no live adapter implemented for exchange '{exchange}'")
    url = base_url or DEFAULT_LIVE_URLS.get(key)
    if url is None:
        raise LiveAdapterError(exchange, f"no default URL for exchange '{exchange}'")
    if key == "okx":
        return cls(credentials, url, dry_run=dry_run, is_demo=is_demo)
    return cls(credentials, url, dry_run=dry_run)
