"""OKX real-time market data stream (public WebSocket, no credentials required).

Connects to the OKX v5 public WebSocket, subscribes to live ticker pushes for
the configured symbols, and writes them into the shared store so the dashboard,
strategies and risk gates consume real-time prices instead of seeded snapshots.

Runs as a background asyncio task inside the FastAPI lifespan. Public market
data only -- no API key/secret needed.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc
from app.models.domain import Ticker

logger = get_logger(__name__)

OKX_PUBLIC_WS_URL = "wss://ws.okx.com:8443/ws/v5/public"
OKX_DEMO_PUBLIC_WS_URL = "wss://wspap.okx.com:8443/ws/v5/public"

# System symbol (Binance-style, no dash) -> OKX instId (dashed)
DEFAULT_SYMBOL_MAP: dict[str, str] = {
    "BTCUSDT": "BTC-USDT",
    "ETHUSDT": "ETH-USDT",
    "BNBUSDT": "BNB-USDT",
    "SOLUSDT": "SOL-USDT",
    "DOGEUSDT": "DOGE-USDT",
    "XRPUSDT": "XRP-USDT",
    "ADAUSDT": "ADA-USDT",
    "LTCUSDT": "LTC-USDT",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OkxMarketStreamService:
    """Streams OKX public tickers into the store over WebSocket."""

    def __init__(self, store: Any, symbol_map: dict[str, str] | None = None, demo: bool = False):
        self._store = store
        self.symbol_map = symbol_map or dict(DEFAULT_SYMBOL_MAP)
        self._reverse_map = {v: k for k, v in self.symbol_map.items()}
        self.demo = demo
        self._ws_url = OKX_DEMO_PUBLIC_WS_URL if demo else OKX_PUBLIC_WS_URL
        # runtime state
        self.running = False
        self.connected = False
        self.last_message_at: str | None = None
        self.last_error: str | None = None
        self.reconnect_count = 0
        self.tick_count = 0
        self._stop_event = asyncio.Event()

    # ── public status ────────────────────────────────────────────────
    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "connected": self.connected,
            "demo": self.demo,
            "ws_url": self._ws_url,
            "symbols": list(self.symbol_map.keys()),
            "tick_count": self.tick_count,
            "reconnect_count": self.reconnect_count,
            "last_message_at": self.last_message_at,
            "last_error": self.last_error,
        }

    def stop(self) -> None:
        self._stop_event.set()

    # ── main loop ────────────────────────────────────────────────────
    async def run_forever(self) -> None:
        """Reconnecting supervisor loop with exponential backoff."""
        self.running = True
        backoff = 1.0
        while not self._stop_event.is_set():
            try:
                await self._connect_and_stream()
                backoff = 1.0  # clean exit resets backoff
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self.connected = False
                self.last_error = str(exc)[:300]
                self.reconnect_count += 1
                logger.warning("okx_stream_disconnected", error=self.last_error, backoff=backoff)
                # wait with backoff, but remain responsive to stop()
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, 30.0)
        self.running = False
        self.connected = False

    async def _connect_and_stream(self) -> None:
        import websockets  # local import so app starts even if lib missing

        args = [{"channel": "tickers", "instId": inst} for inst in self.symbol_map.values()]
        async with websockets.connect(self._ws_url, open_timeout=10, ping_interval=None) as ws:
            await ws.send(json.dumps({"op": "subscribe", "args": args}))
            self.connected = True
            self.last_error = None
            logger.info("okx_stream_connected", url=self._ws_url, symbols=len(args), demo=self.demo)

            async def _heartbeat():
                # OKX requires an application-level "ping" string every ~30s
                while not self._stop_event.is_set():
                    await asyncio.sleep(25)
                    try:
                        await ws.send("ping")
                    except Exception:  # noqa: BLE001
                        return

            hb_task = asyncio.create_task(_heartbeat())
            try:
                async for raw in ws:
                    if self._stop_event.is_set():
                        break
                    self._handle_raw(raw)
            finally:
                hb_task.cancel()
                self.connected = False

    # ── message handling ─────────────────────────────────────────────
    def _handle_raw(self, raw: str | bytes) -> None:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        text = raw.strip()
        if text == "pong":
            return
        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            return
        # subscription / error frames carry "event"
        if "event" in msg:
            if msg.get("event") == "error":
                self.last_error = f"{msg.get('code')}: {msg.get('msg')}"[:300]
                logger.warning("okx_stream_error_frame", error=self.last_error)
            return
        arg = msg.get("arg", {})
        if arg.get("channel") != "tickers":
            return
        for item in msg.get("data", []) or []:
            self._ingest_ticker(item)

    def _ingest_ticker(self, item: dict[str, Any]) -> None:
        inst_id = item.get("instId", "")
        symbol = self._reverse_map.get(inst_id)
        if symbol is None or symbol not in self._store.symbols:
            return
        last = str(item.get("last", "0"))
        bid = str(item.get("bidPx") or last)
        ask = str(item.get("askPx") or last)
        vol = str(item.get("vol24h", "0"))
        high = str(item.get("high24h", "0"))
        low = str(item.get("low24h", "0"))
        change = self._pct_change(last, item.get("open24h"))
        now = _utcnow()
        with self._store.get_lock():
            seq = getattr(self._store.market_service, "sequence", 0) + 1
            self._store.tickers[symbol] = Ticker(
                symbol=symbol,
                last_price=last,
                bid_price=bid,
                ask_price=ask,
                volume_24h=vol,
                change_24h=change,
                high_24h=high,
                low_24h=low,
                source="okx-ws-demo" if self.demo else "okx-ws",
                event_time=now,
                ingest_time=now,
                sequence=seq,
            )
            self._store.market_service.sequence = seq
            self._store.market_service.last_refresh_at = now.isoformat()
            self._store.market_service.last_source = "okx-ws-demo" if self.demo else "okx-ws"
        self.tick_count += 1
        self.last_message_at = now.isoformat()

    @staticmethod
    def _pct_change(last: str, open_24h: Any) -> str:
        try:
            if open_24h in (None, "", 0, "0"):
                return "+0.00"
            pct = (float(last) - float(open_24h)) / float(open_24h) * 100
            return f"{pct:+.2f}"
        except (ValueError, TypeError, ZeroDivisionError):
            return "+0.00"

    def publish_snapshot_event(self) -> None:
        """Emit a domain event so observability/audit can track the stream."""
        event_bus.publish(DomainEvent(
            event_type=event_type("market", "okx_stream_status"),
            event_id=new_event_id("market"),
            event_time=now_utc(),
            version=1,
            actor="system",
            resource_type="market_stream",
            resource_id="okx",
            payload=self.status(),
        ))
