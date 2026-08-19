"""WebSocket connection and stream manager for Binance and OKX live exchanges.

Provides:
- `BinanceWebSocketClient`: market data and user data stream (executionReport) subscription,
  message parsing, and 30-minute listenKey keepalive lifecycle.
- `OkxWebSocketClient`: public channels, private channel login authentication (`op: login`),
  orders/account/positions subscription, and ping-pong heartbeat.
- `WebSocketManager`: unified registry and dispatcher for active exchange WS streams.
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from app.adapters.live_exchange_adapters import BinanceLiveAdapter, OkxLiveAdapter

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BinanceWebSocketClient:
    """Binance WebSocket client for market data & UserDataStream."""

    SPOT_WS_BASE = "wss://stream.binance.com:9443/ws"
    FUTURES_WS_BASE = "wss://fstream.binance.com/ws"
    SPOT_TESTNET_WS_BASE = "wss://testnet.binance.vision/ws"
    FUTURES_TESTNET_WS_BASE = "wss://stream.binancefuture.com/ws"

    def __init__(
        self,
        adapter: BinanceLiveAdapter | None = None,
        is_contract: bool = False,
        testnet: bool = False,
    ):
        self.adapter = adapter
        self.is_contract = is_contract
        self.testnet = testnet
        self._connected = False
        self._listen_key: str | None = None
        self._callbacks: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self._keepalive_task: threading.Timer | None = None
        self._keepalive_interval = 1800  # 30 minutes in seconds
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def listen_key(self) -> str | None:
        return self._listen_key

    def get_ws_url(self, listen_key: str | None = None) -> str:
        """Get the base or user stream WebSocket URL."""
        if self.is_contract:
            base = self.FUTURES_TESTNET_WS_BASE if self.testnet else self.FUTURES_WS_BASE
        else:
            base = self.SPOT_TESTNET_WS_BASE if self.testnet else self.SPOT_WS_BASE
        if listen_key:
            return f"{base}/{listen_key}"
        return base

    def build_market_stream_url(self, symbols: list[str], channels: list[str]) -> str:
        """Construct multi-stream URL for market data (e.g. btcusdt@ticker/ethusdt@kline_1m)."""
        base = self.get_ws_url()
        streams = []
        for symbol in symbols:
            s_clean = symbol.lower().replace("-", "").replace("/", "")
            for ch in channels:
                streams.append(f"{s_clean}@{ch}")
        if len(streams) == 1:
            return f"{base}/{streams[0]}"
        return f"{base}/stream?streams=" + "/".join(streams)

    def build_subscribe_message(self, streams: list[str], req_id: int = 1) -> dict[str, Any]:
        """Generate JSON payload to subscribe to streams dynamically."""
        return {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": req_id,
        }

    def build_unsubscribe_message(self, streams: list[str], req_id: int = 1) -> dict[str, Any]:
        """Generate JSON payload to unsubscribe from streams dynamically."""
        return {
            "method": "UNSUBSCRIBE",
            "params": streams,
            "id": req_id,
        }

    def register_callback(self, event_type: str, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback for a specific event type (e.g. executionReport, kline, trade)."""
        with self._lock:
            if event_type not in self._callbacks:
                self._callbacks[event_type] = []
            self._callbacks[event_type].append(callback)

    def dispatch(self, parsed_event: dict[str, Any]) -> None:
        """Dispatch a parsed event to registered callbacks."""
        event_type = parsed_event.get("event_type", "unknown")
        callbacks_to_call = []
        with self._lock:
            callbacks_to_call.extend(self._callbacks.get(event_type, []))
            callbacks_to_call.extend(self._callbacks.get("*", []))
        for cb in callbacks_to_call:
            try:
                cb(parsed_event)
            except Exception as e:
                logger.error("Error in Binance WS callback for %s: %s", event_type, e)

    def parse_message(self, raw_msg: str | dict[str, Any]) -> dict[str, Any]:
        """Parse incoming Binance WS message into standardized dictionary."""
        if isinstance(raw_msg, str):
            try:
                msg = json.loads(raw_msg)
            except json.JSONDecodeError:
                return {"event_type": "raw", "data": raw_msg}
        else:
            msg = raw_msg

        # Handle combined stream envelope {"stream": "...", "data": {...}}
        if "stream" in msg and "data" in msg:
            data = msg["data"]
            stream_name = msg["stream"]
        else:
            data = msg
            stream_name = ""

        event = data.get("e")
        if event == "executionReport":
            # Spot order execution report
            return {
                "event_type": "executionReport",
                "exchange": "binance",
                "market_type": "spot",
                "symbol": data.get("s", ""),
                "client_order_id": data.get("c", ""),
                "order_id": str(data.get("i", "")),
                "side": data.get("S", "").lower(),
                "order_type": data.get("o", "").lower(),
                "order_status": data.get("X", "").lower(),
                "reject_reason": data.get("r", "NONE"),
                "quantity": str(data.get("q", "0")),
                "price": str(data.get("p", "0")),
                "filled_quantity": str(data.get("z", "0")),
                "last_filled_quantity": str(data.get("l", "0")),
                "last_filled_price": str(data.get("L", "0")),
                "commission": str(data.get("n", "0")),
                "commission_asset": data.get("N", ""),
                "trade_id": str(data.get("t", "")),
                "event_time": data.get("E", int(time.time() * 1000)),
                "raw": data,
            }
        elif event == "ORDER_TRADE_UPDATE":
            # Futures order trade update
            order_data = data.get("o", {})
            return {
                "event_type": "executionReport",
                "exchange": "binance",
                "market_type": "future",
                "symbol": order_data.get("s", ""),
                "client_order_id": order_data.get("c", ""),
                "order_id": str(order_data.get("i", "")),
                "side": order_data.get("S", "").lower(),
                "order_type": order_data.get("o", "").lower(),
                "order_status": order_data.get("X", "").lower(),
                "quantity": str(order_data.get("q", "0")),
                "price": str(order_data.get("p", "0")),
                "filled_quantity": str(order_data.get("z", "0")),
                "last_filled_quantity": str(order_data.get("l", "0")),
                "last_filled_price": str(order_data.get("L", "0")),
                "average_price": str(order_data.get("ap", "0")),
                "commission": str(order_data.get("n", "0")),
                "commission_asset": order_data.get("N", ""),
                "trade_id": str(order_data.get("t", "")),
                "realized_profit": str(order_data.get("rp", "0")),
                "event_time": data.get("E", int(time.time() * 1000)),
                "raw": data,
            }
        elif event == "ACCOUNT_UPDATE" or event == "outboundAccountPosition":
            return {
                "event_type": "accountUpdate",
                "exchange": "binance",
                "event_time": data.get("E", int(time.time() * 1000)),
                "balances": data.get("B", data.get("a", {}).get("B", [])),
                "positions": data.get("a", {}).get("P", []),
                "raw": data,
            }
        elif event == "kline":
            k = data.get("k", {})
            return {
                "event_type": "kline",
                "exchange": "binance",
                "symbol": data.get("s", ""),
                "interval": k.get("i", ""),
                "open": str(k.get("o", "0")),
                "high": str(k.get("h", "0")),
                "low": str(k.get("l", "0")),
                "close": str(k.get("c", "0")),
                "volume": str(k.get("v", "0")),
                "is_closed": k.get("x", False),
                "open_time": k.get("t", 0),
                "close_time": k.get("T", 0),
                "raw": data,
            }
        elif event == "trade":
            return {
                "event_type": "trade",
                "exchange": "binance",
                "symbol": data.get("s", ""),
                "trade_id": str(data.get("t", "")),
                "price": str(data.get("p", "0")),
                "quantity": str(data.get("q", "0")),
                "event_time": data.get("E", int(time.time() * 1000)),
                "raw": data,
            }
        elif event == "24hrTicker":
            return {
                "event_type": "ticker",
                "exchange": "binance",
                "symbol": data.get("s", ""),
                "last_price": str(data.get("c", "0")),
                "bid_price": str(data.get("b", "0")),
                "ask_price": str(data.get("a", "0")),
                "volume_24h": str(data.get("v", "0")),
                "event_time": data.get("E", int(time.time() * 1000)),
                "raw": data,
            }
        elif "result" in data or "id" in data:
            return {
                "event_type": "subscriptionResponse",
                "id": data.get("id"),
                "result": data.get("result"),
                "raw": data,
            }
        return {"event_type": event or "generic", "data": data, "stream": stream_name}

    # ── Keepalive & Lifecycle ────────────────────────────────────────

    def start_user_data_stream(self, adapter: BinanceLiveAdapter | None = None) -> str:
        """Create listenKey via REST and start the 30-minute keepalive loop."""
        ad = adapter or self.adapter
        if ad is None:
            raise ValueError("Binance adapter required to create listenKey")
        self._listen_key = ad.create_listen_key(is_contract=self.is_contract)
        self._connected = True
        self._start_keepalive_timer(ad)
        return self._listen_key

    def _start_keepalive_timer(self, adapter: BinanceLiveAdapter) -> None:
        """Start recurring timer to keep listenKey alive every 30 minutes."""
        self.stop_keepalive()
        def _tick():
            try:
                if self._listen_key:
                    adapter.keepalive_listen_key(self._listen_key, is_contract=self.is_contract)
                    logger.info("Binance listenKey keepalive succeeded for %s", self._listen_key)
            except Exception as exc:
                logger.warning("Binance listenKey keepalive error: %s", exc)
            with self._lock:
                if self._connected and self._listen_key:
                    self._keepalive_task = threading.Timer(self._keepalive_interval, _tick)
                    self._keepalive_task.daemon = True
                    self._keepalive_task.start()

        with self._lock:
            self._keepalive_task = threading.Timer(self._keepalive_interval, _tick)
            self._keepalive_task.daemon = True
            self._keepalive_task.start()

    def stop_keepalive(self) -> None:
        """Stop keepalive timer."""
        with self._lock:
            if self._keepalive_task:
                self._keepalive_task.cancel()
                self._keepalive_task = None

    def close(self, adapter: BinanceLiveAdapter | None = None) -> None:
        """Close listenKey on exchange and stop keepalive."""
        self.stop_keepalive()
        ad = adapter or self.adapter
        if ad and self._listen_key:
            try:
                ad.close_listen_key(self._listen_key, is_contract=self.is_contract)
            except Exception as e:
                logger.warning("Error closing Binance listenKey: %s", e)
        self._listen_key = None
        self._connected = False


class OkxWebSocketClient:
    """OKX v5 WebSocket client for public channels & private authenticated stream."""

    PUBLIC_WS_URL = "wss://ws.okx.com:8443/ws/v5/public"
    PRIVATE_WS_URL = "wss://ws.okx.com:8443/ws/v5/private"
    BUSINESS_WS_URL = "wss://ws.okx.com:8443/ws/v5/business"
    DEMO_PUBLIC_WS_URL = "wss://wspap.okx.com:8443/ws/v5/public"
    DEMO_PRIVATE_WS_URL = "wss://wspap.okx.com:8443/ws/v5/private"

    def __init__(
        self,
        adapter: OkxLiveAdapter | None = None,
        demo: bool = False,
    ):
        self.adapter = adapter
        self.demo = demo
        self._connected = False
        self._authenticated = False
        self._callbacks: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    def get_public_ws_url(self) -> str:
        return self.DEMO_PUBLIC_WS_URL if self.demo else self.PUBLIC_WS_URL

    def get_private_ws_url(self) -> str:
        return self.DEMO_PRIVATE_WS_URL if self.demo else self.PRIVATE_WS_URL

    def build_login_message(self, adapter: OkxLiveAdapter | None = None, timestamp: str | None = None) -> dict[str, Any]:
        """Generate WebSocket login authentication frame."""
        ad = adapter or self.adapter
        if ad is None:
            raise ValueError("OKX adapter required for login frame")
        auth_params = ad.get_ws_auth_params(timestamp=timestamp)
        return {
            "op": "login",
            "args": [auth_params],
        }

    def build_subscribe_message(self, args: list[dict[str, str]]) -> dict[str, Any]:
        """Construct JSON subscribe message."""
        return {
            "op": "subscribe",
            "args": args,
        }

    def build_unsubscribe_message(self, args: list[dict[str, str]]) -> dict[str, Any]:
        """Construct JSON unsubscribe message."""
        return {
            "op": "unsubscribe",
            "args": args,
        }

    def build_private_subscribe_message(
        self,
        channels: list[str] = ("orders", "account", "positions"),
        inst_type: str = "ANY",
    ) -> dict[str, Any]:
        """Generate subscription frame for standard private trading channels."""
        args = []
        for ch in channels:
            item = {"channel": ch}
            if ch in ("orders", "positions"):
                item["instType"] = inst_type
            args.append(item)
        return self.build_subscribe_message(args)

    def ping(self) -> str:
        """OKX heartbeat ping string."""
        return "ping"

    def register_callback(self, event_type: str, callback: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            if event_type not in self._callbacks:
                self._callbacks[event_type] = []
            self._callbacks[event_type].append(callback)

    def dispatch(self, parsed_event: dict[str, Any]) -> None:
        event_type = parsed_event.get("event_type", "unknown")
        callbacks_to_call = []
        with self._lock:
            callbacks_to_call.extend(self._callbacks.get(event_type, []))
            callbacks_to_call.extend(self._callbacks.get("*", []))
        for cb in callbacks_to_call:
            try:
                cb(parsed_event)
            except Exception as e:
                logger.error("Error in OKX WS callback for %s: %s", event_type, e)

    def parse_message(self, raw_msg: str | dict[str, Any]) -> dict[str, Any]:
        """Parse incoming OKX v5 WS message."""
        if isinstance(raw_msg, str):
            if raw_msg.strip() == "pong":
                return {"event_type": "pong", "exchange": "okx"}
            try:
                msg = json.loads(raw_msg)
            except json.JSONDecodeError:
                return {"event_type": "raw", "data": raw_msg}
        else:
            msg = raw_msg

        event = msg.get("event")
        if event == "login":
            code = str(msg.get("code", "0"))
            success = (code == "0")
            self._authenticated = success
            return {
                "event_type": "login",
                "exchange": "okx",
                "success": success,
                "code": code,
                "msg": msg.get("msg", ""),
                "raw": msg,
            }
        elif event in ("subscribe", "unsubscribe"):
            return {
                "event_type": event,
                "exchange": "okx",
                "arg": msg.get("arg", {}),
                "raw": msg,
            }
        elif event == "error":
            return {
                "event_type": "error",
                "exchange": "okx",
                "code": msg.get("code"),
                "msg": msg.get("msg"),
                "raw": msg,
            }

        # Data push frames: {"arg": {"channel": "..."}, "data": [...]}
        arg = msg.get("arg", {})
        channel = arg.get("channel", "")
        data_list = msg.get("data", [])

        if channel == "orders":
            orders = []
            for item in data_list:
                state_map = {
                    "live": "new",
                    "partially_filled": "partially_filled",
                    "filled": "filled",
                    "canceled": "cancelled",
                }
                orders.append({
                    "symbol": item.get("instId", ""),
                    "client_order_id": item.get("clOrdId", ""),
                    "order_id": str(item.get("ordId", "")),
                    "side": item.get("side", "").lower(),
                    "order_type": item.get("ordType", "").lower(),
                    "order_status": state_map.get(item.get("state", "live"), item.get("state", "unknown")),
                    "quantity": str(item.get("sz", "0")),
                    "price": str(item.get("px", "0")),
                    "filled_quantity": str(item.get("accFillSz", "0")),
                    "average_price": str(item.get("avgPx", "0")) if item.get("avgPx") else None,
                    "fee": str(item.get("fee", "0")),
                    "fee_currency": item.get("feeCcy", ""),
                    "trade_id": str(item.get("tradeId", "")),
                    "update_time": item.get("uTime", ""),
                })
            return {
                "event_type": "executionReport",
                "exchange": "okx",
                "channel": channel,
                "orders": orders,
                "raw": msg,
            }
        elif channel == "account":
            return {
                "event_type": "accountUpdate",
                "exchange": "okx",
                "channel": channel,
                "data": data_list,
                "raw": msg,
            }
        elif channel == "positions":
            positions = []
            for item in data_list:
                positions.append({
                    "symbol": item.get("instId", ""),
                    "position": str(item.get("pos", "0")),
                    "pos_side": item.get("posSide", "net"),
                    "available_position": str(item.get("availPos", "0")),
                    "average_price": str(item.get("avgPx", "0")),
                    "unrealized_pnl": str(item.get("upl", "0")),
                    "liquidation_price": str(item.get("liqPx", "0")),
                })
            return {
                "event_type": "positionUpdate",
                "exchange": "okx",
                "channel": channel,
                "positions": positions,
                "raw": msg,
            }
        elif channel == "tickers":
            tickers = []
            for item in data_list:
                tickers.append({
                    "symbol": item.get("instId", ""),
                    "last_price": str(item.get("last", "0")),
                    "bid_price": str(item.get("bidPx", "0")),
                    "ask_price": str(item.get("askPx", "0")),
                    "volume_24h": str(item.get("vol24h", "0")),
                    "timestamp": item.get("ts", ""),
                })
            return {
                "event_type": "ticker",
                "exchange": "okx",
                "channel": channel,
                "tickers": tickers,
                "raw": msg,
            }
        elif channel.startswith("candle"):
            return {
                "event_type": "kline",
                "exchange": "okx",
                "channel": channel,
                "candles": data_list,
                "raw": msg,
            }

        return {
            "event_type": channel or "push",
            "exchange": "okx",
            "data": data_list,
            "raw": msg,
        }


class WebSocketManager:
    """Registry and lifecycle manager for all exchange WebSocket connections."""

    def __init__(self):
        self._clients: dict[str, Any] = {}
        self._lock = threading.Lock()

    def register_client(self, name: str, client: Any) -> None:
        with self._lock:
            self._clients[name.lower()] = client

    def get_client(self, name: str) -> Any | None:
        with self._lock:
            return self._clients.get(name.lower())

    def create_binance_client(
        self,
        adapter: BinanceLiveAdapter | None = None,
        is_contract: bool = False,
        testnet: bool = False,
        name: str = "binance",
    ) -> BinanceWebSocketClient:
        client = BinanceWebSocketClient(adapter=adapter, is_contract=is_contract, testnet=testnet)
        self.register_client(name, client)
        return client

    def create_okx_client(
        self,
        adapter: OkxLiveAdapter | None = None,
        demo: bool = False,
        name: str = "okx",
    ) -> OkxWebSocketClient:
        client = OkxWebSocketClient(adapter=adapter, demo=demo)
        self.register_client(name, client)
        return client

    def close_all(self) -> None:
        with self._lock:
            for client in self._clients.values():
                if hasattr(client, "close"):
                    try:
                        client.close()
                    except Exception as e:
                        logger.warning("Error closing WS client: %s", e)
                elif hasattr(client, "stop_keepalive"):
                    client.stop_keepalive()
            self._clients.clear()

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                name: {
                    "type": type(c).__name__,
                    "connected": getattr(c, "is_connected", False),
                    "authenticated": getattr(c, "is_authenticated", False),
                }
                for name, c in self._clients.items()
            }
