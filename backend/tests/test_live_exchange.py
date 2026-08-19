import hashlib
import hmac
import json
import os
from base64 import b64encode
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.adapters.live_exchange_adapters import (
    BinanceLiveAdapter,
    LiveAdapterError,
    OkxLiveAdapter,
)
from app.adapters.protocol import (
    AdapterConnectionStatus,
    AdapterOrderStatus,
    OrderResult,
)
from app.adapters.websocket_manager import (
    BinanceWebSocketClient,
    OkxWebSocketClient,
    WebSocketManager,
)
from app.db.memory import get_store
from app.main import app
from app.services.live_mode_service import LiveTradingGateError, SafetyGate


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ════════════════════════════════════════════════════════════════════
# 1. Binance Sign & REST Tests
# ════════════════════════════════════════════════════════════════════

class TestBinanceSigning:
    """Validate Binance HMAC-SHA256 signature algorithms against official specifications."""

    def test_binance_official_signature_vector(self):
        api_key = "test_binance_api_key_12345"
        api_secret = "test_binance_api_secret_67890"
        adapter = BinanceLiveAdapter(
            {"api_key": api_key, "api_secret": api_secret},
            base_url="https://api.binance.com",
        )

        params = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "quantity": "1.00",
            "price": "50000.00",
            "timeInForce": "GTC",
            "timestamp": 1600000000000,
            "recvWindow": 5000,
        }
        signed = adapter.sign("POST", "/api/v3/order", params=params, timestamp=1600000000000, recv_window=5000)

        # Re-compute expected query and HMAC-SHA256 signature
        import urllib.parse
        expected_query = urllib.parse.urlencode(params)
        expected_sig = hmac.new(api_secret.encode("utf-8"), expected_query.encode("utf-8"), hashlib.sha256).hexdigest()

        assert signed["signature"] == expected_sig
        assert f"signature={expected_sig}" in signed["query"]
        assert signed["headers"]["X-MBX-APIKEY"] == api_key
        assert signed["headers"]["Content-Type"] == "application/json"
        assert signed["url"].startswith("https://api.binance.com/api/v3/order?")

    def test_binance_futures_signature_format(self):
        adapter = BinanceLiveAdapter(
            {"api_key": "key_futures", "api_secret": "secret_futures"},
            base_url="https://fapi.binance.com",
        )
        params = {"symbol": "ETHUSDT", "side": "SELL", "quantity": "2.5"}
        signed = adapter.sign("POST", "/fapi/v1/order", params=params, timestamp=1700000000000, recv_window=5000)
        assert signed["headers"]["X-MBX-APIKEY"] == "key_futures"
        assert "timestamp=1700000000000" in signed["query"]
        assert "signature=" in signed["query"]

    def test_binance_missing_credentials_raises(self):
        adapter = BinanceLiveAdapter({}, base_url="https://api.binance.com")
        with pytest.raises(LiveAdapterError) as exc_info:
            adapter.sign("GET", "/api/v3/account")
        assert "missing api_key/api_secret" in str(exc_info.value)


class TestBinanceRestOperations:
    """Test Binance Spot & Futures REST methods, error handling and data serialization."""

    def test_binance_spot_order_serialization(self):
        adapter = BinanceLiveAdapter(
            {"api_key": "k", "api_secret": "s"},
            base_url="https://api.binance.com",
        )
        adapter._status = AdapterConnectionStatus.CONNECTED

        mock_resp = {
            "symbol": "BTCUSDT",
            "orderId": 12345678,
            "clientOrderId": "cl_ord_001",
            "status": "FILLED",
            "executedQty": "0.5000",
            "cummulativeQuoteQty": "25000.00",
        }

        with patch.object(adapter, "_request", return_value=mock_resp):
            res = adapter.place_order("cl_ord_001", "BTCUSDT", "buy", "0.5000", price="50000.00")
            assert isinstance(res, OrderResult)
            assert res.client_order_id == "cl_ord_001"
            assert res.status == AdapterOrderStatus.FILLED
            assert res.filled_quantity == "0.5000"
            assert res.average_price == "50000.00"
            assert res.exchange == "binance"

    def test_binance_futures_order_and_positions(self):
        adapter = BinanceLiveAdapter(
            {"api_key": "k", "api_secret": "s"},
            base_url="https://fapi.binance.com",
        )
        adapter._status = AdapterConnectionStatus.CONNECTED

        # Test futures order
        mock_order_resp = {
            "symbol": "ETHUSDT",
            "orderId": 88888,
            "clientOrderId": "f_cl_002",
            "status": "NEW",
            "executedQty": "0",
            "avgPrice": "0",
        }
        with patch.object(adapter, "_request", return_value=mock_order_resp):
            res = adapter.place_order("f_cl_002", "ETHUSDT", "sell", "1.0", price="3000.00", is_contract=True)
            assert res.status == AdapterOrderStatus.NEW
            assert "futures" in res.text

        # Test futures positionRisk
        mock_positions = [
            {"symbol": "BTCUSDT", "positionAmt": "0.150", "entryPrice": "51000"},
            {"symbol": "ETHUSDT", "positionAmt": "0.000", "entryPrice": "0"},
            {"symbol": "SOLUSDT", "positionAmt": "-5.000", "entryPrice": "140"},
        ]
        with patch.object(adapter, "_request", return_value=mock_positions):
            positions = adapter.get_positions(is_contract=True)
            assert positions == {"BTCUSDT": "0.150", "SOLUSDT": "-5.000"}

        # Test futures balance
        mock_balance = [
            {"asset": "USDT", "balance": "10000.50", "availableBalance": "8500.25"},
            {"asset": "BNB", "balance": "10.0", "availableBalance": "10.0"},
        ]
        with patch.object(adapter, "_request", return_value=mock_balance):
            avail = adapter.get_balance("USDT", is_contract=True)
            assert avail == "8500.25"

    def test_binance_listen_key_lifecycle(self):
        adapter = BinanceLiveAdapter(
            {"api_key": "k", "api_secret": "s"},
            base_url="https://api.binance.com",
        )

        with patch.object(adapter, "_request", return_value={"listenKey": "test_listen_key_spot_999"}):
            key = adapter.create_listen_key(is_contract=False)
            assert key == "test_listen_key_spot_999"

        with patch.object(adapter, "_request", return_value={}):
            ok = adapter.keepalive_listen_key("test_listen_key_spot_999", is_contract=False)
            assert ok is True

        with patch.object(adapter, "_request", return_value={}):
            ok = adapter.close_listen_key("test_listen_key_spot_999", is_contract=False)
            assert ok is True

    def test_binance_dry_run_guards_submission(self):
        adapter = BinanceLiveAdapter(
            {"api_key": "k", "api_secret": "s"},
            base_url="https://api.binance.com",
            dry_run=True,
        )
        adapter._status = AdapterConnectionStatus.CONNECTED
        with pytest.raises(LiveAdapterError) as exc_info:
            adapter.place_order("dry_001", "BTCUSDT", "buy", "0.01", "50000")
        assert "dry-run mode" in str(exc_info.value)


# ════════════════════════════════════════════════════════════════════
# 2. OKX v5 Sign & REST Tests
# ════════════════════════════════════════════════════════════════════

class TestOkxSigning:
    """Validate OKX v5 HMAC-SHA256 Base64 signing and header injection."""

    def test_okx_official_signature_vector(self):
        api_key = "test_okx_key_abc"
        api_secret = "test_okx_secret_xyz"
        passphrase = "test_okx_passphrase"
        adapter = OkxLiveAdapter(
            {"api_key": api_key, "api_secret": api_secret, "passphrase": passphrase},
            base_url="https://www.okx.com",
        )

        ts = "2026-08-18T02:35:00.000Z"
        body = {"instId": "BTC-USDT", "tdMode": "cash", "side": "buy", "ordType": "limit", "sz": "1"}

        headers = adapter.sign("POST", "/api/v5/trade/order", body=body, timestamp=ts)

        # Prehash: timestamp + METHOD + path + body_str
        expected_body_str = json.dumps(body, separators=(",", ":"))
        expected_prehash = f"{ts}POST/api/v5/trade/order{expected_body_str}"
        expected_sign = b64encode(hmac.new(api_secret.encode("utf-8"), expected_prehash.encode("utf-8"), hashlib.sha256).digest()).decode("utf-8")

        assert headers["OK-ACCESS-KEY"] == api_key
        assert headers["OK-ACCESS-SIGN"] == expected_sign
        assert headers["OK-ACCESS-TIMESTAMP"] == ts
        assert headers["OK-ACCESS-PASSPHRASE"] == passphrase

    def test_okx_get_request_signing_with_params(self):
        adapter = OkxLiveAdapter(
            {"api_key": "k", "api_secret": "s", "passphrase": "p"},
            base_url="https://www.okx.com",
        )
        ts = "2026-08-18T02:35:00.123Z"
        params = {"ccy": "BTC"}
        headers = adapter.sign("GET", "/api/v5/account/balance", params=params, timestamp=ts)

        expected_prehash = f"{ts}GET/api/v5/account/balance?ccy=BTC"
        expected_sign = b64encode(hmac.new("s".encode("utf-8"), expected_prehash.encode("utf-8"), hashlib.sha256).digest()).decode("utf-8")

        assert headers["OK-ACCESS-SIGN"] == expected_sign

    def test_okx_ws_auth_params(self):
        adapter = OkxLiveAdapter(
            {"api_key": "k", "api_secret": "s", "passphrase": "p"},
            base_url="https://www.okx.com",
        )
        ts = "1700000000.5"
        auth_params = adapter.get_ws_auth_params(timestamp=ts)

        expected_prehash = f"{ts}GET/users/self/verify"
        expected_sign = b64encode(hmac.new("s".encode("utf-8"), expected_prehash.encode("utf-8"), hashlib.sha256).digest()).decode("utf-8")

        assert auth_params["apiKey"] == "k"
        assert auth_params["passphrase"] == "p"
        assert auth_params["timestamp"] == ts
        assert auth_params["sign"] == expected_sign


class TestOkxRestOperations:
    """Test OKX v5 Spot & SWAP Perpetual operations."""

    def test_okx_spot_and_swap_order_placement(self):
        adapter = OkxLiveAdapter(
            {"api_key": "k", "api_secret": "s", "passphrase": "p"},
            base_url="https://www.okx.com",
        )
        adapter._status = AdapterConnectionStatus.CONNECTED

        # 1. Spot Order
        mock_spot_resp = {"data": [{"sCode": "0", "ordId": "okx_ord_111"}]}
        with patch.object(adapter, "_request", return_value=mock_spot_resp) as mock_req:
            res = adapter.place_order("okx_cl_1", "BTC-USDT", "buy", "0.05", price="50000")
            assert res.status == AdapterOrderStatus.NEW
            assert "okx_ord_111" in res.text
            body = mock_req.call_args[1]["body"]
            assert body["tdMode"] == "cash"
            assert body["instId"] == "BTC-USDT"

        # 2. SWAP Contract Order
        mock_swap_resp = {"data": [{"sCode": "0", "ordId": "okx_swap_222"}]}
        with patch.object(adapter, "_request", return_value=mock_swap_resp) as mock_req:
            res = adapter.place_order("okx_cl_2", "BTC-USDT-SWAP", "sell", "10", price="51000", is_contract=True, pos_side="net")
            assert res.status == AdapterOrderStatus.NEW
            body = mock_req.call_args[1]["body"]
            assert body["tdMode"] == "cross"
            assert body["posSide"] == "net"

    def test_okx_get_positions_and_balance(self):
        adapter = OkxLiveAdapter(
            {"api_key": "k", "api_secret": "s", "passphrase": "p"},
            base_url="https://www.okx.com",
        )
        adapter._status = AdapterConnectionStatus.CONNECTED

        # Test SWAP positions
        mock_positions = {
            "data": [
                {"instId": "ETH-USDT-SWAP", "pos": "5.0"},
                {"instId": "SOL-USDT-SWAP", "pos": "-20.0"},
            ]
        }
        with patch.object(adapter, "_request", return_value=mock_positions):
            positions = adapter.get_positions(inst_type="SWAP")
            assert positions == {"ETH-USDT-SWAP": "5.0", "SOL-USDT-SWAP": "-20.0"}

        # Test balance
        mock_balance = {
            "data": [
                {
                    "totalEq": "50000.00",
                    "details": [
                        {"ccy": "USDT", "availBal": "35000.50"},
                        {"ccy": "BTC", "availBal": "0.3"},
                    ],
                }
            ]
        }
        with patch.object(adapter, "_request", return_value=mock_balance):
            avail = adapter.get_balance("USDT")
            assert avail == "35000.50"
            acct = adapter.get_account_balance()
            assert acct["total_equity"] == "50000.00"


# ════════════════════════════════════════════════════════════════════
# 3. WebSocket Manager & Clients Tests
# ════════════════════════════════════════════════════════════════════

class TestWebSocketManagerAndClients:
    """Test Binance & OKX WebSocket clients, parsing, and keepalive management."""

    def test_binance_ws_url_and_subscriptions(self):
        client = BinanceWebSocketClient(is_contract=False, testnet=False)
        assert client.get_ws_url() == "wss://stream.binance.com:9443/ws"
        assert client.get_ws_url("my_listen_key") == "wss://stream.binance.com:9443/ws/my_listen_key"

        stream_url = client.build_market_stream_url(["BTCUSDT", "ETHUSDT"], ["ticker", "kline_1m"])
        assert "btcusdt@ticker" in stream_url
        assert "ethusdt@kline_1m" in stream_url

        sub_msg = client.build_subscribe_message(["btcusdt@trade"], req_id=42)
        assert sub_msg == {"method": "SUBSCRIBE", "params": ["btcusdt@trade"], "id": 42}

    def test_binance_ws_message_parsing(self):
        client = BinanceWebSocketClient()

        # 1. executionReport
        exec_payload = {
            "e": "executionReport",
            "E": 1499405658658,
            "s": "ETHBTC",
            "c": "mUvoqJxViewxRqu7G0qUmQ",
            "S": "BUY",
            "o": "LIMIT",
            "X": "FILLED",
            "q": "1.00000000",
            "p": "0.10264410",
            "z": "1.00000000",
            "L": "0.10264410",
            "n": "0.00100000",
            "N": "BNB",
            "i": 4293153,
        }
        parsed = client.parse_message(exec_payload)
        assert parsed["event_type"] == "executionReport"
        assert parsed["symbol"] == "ETHBTC"
        assert parsed["client_order_id"] == "mUvoqJxViewxRqu7G0qUmQ"
        assert parsed["order_status"] == "filled"
        assert parsed["filled_quantity"] == "1.00000000"
        assert parsed["commission"] == "0.00100000"

        # 2. kline
        kline_payload = {
            "e": "kline",
            "s": "BTCUSDT",
            "k": {
                "t": 123400000,
                "T": 123460000,
                "s": "BTCUSDT",
                "i": "1m",
                "o": "50000",
                "c": "50100",
                "h": "50200",
                "l": "49900",
                "v": "15.5",
                "x": True,
            },
        }
        parsed_k = client.parse_message(kline_payload)
        assert parsed_k["event_type"] == "kline"
        assert parsed_k["close"] == "50100"
        assert parsed_k["is_closed"] is True

    def test_okx_ws_login_and_channels(self):
        adapter = OkxLiveAdapter(
            {"api_key": "k", "api_secret": "s", "passphrase": "p"},
            base_url="https://www.okx.com",
        )
        client = OkxWebSocketClient(adapter=adapter)

        # Login Frame
        login_msg = client.build_login_message(timestamp="1700000000.000")
        assert login_msg["op"] == "login"
        assert len(login_msg["args"]) == 1
        assert login_msg["args"][0]["apiKey"] == "k"
        assert login_msg["args"][0]["passphrase"] == "p"

        # Private subscription
        priv_sub = client.build_private_subscribe_message(["orders", "positions"])
        assert priv_sub["op"] == "subscribe"
        assert any(a["channel"] == "orders" for a in priv_sub["args"])
        assert any(a["channel"] == "positions" for a in priv_sub["args"])

        # Ping
        assert client.ping() == "ping"

    def test_okx_ws_message_parsing(self):
        client = OkxWebSocketClient()

        # 1. Login success
        login_raw = {"event": "login", "code": "0", "msg": ""}
        res = client.parse_message(login_raw)
        assert res["event_type"] == "login"
        assert res["success"] is True

        # 2. Pong
        res_pong = client.parse_message("pong")
        assert res_pong["event_type"] == "pong"

        # 3. Orders push
        orders_raw = {
            "arg": {"channel": "orders", "instType": "SPOT"},
            "data": [
                {
                    "instId": "BTC-USDT",
                    "ordId": "999888",
                    "clOrdId": "okx_cl_test",
                    "state": "filled",
                    "side": "buy",
                    "sz": "0.1",
                    "px": "50000",
                    "accFillSz": "0.1",
                    "avgPx": "50000",
                    "fee": "-0.05",
                    "feeCcy": "USDT",
                }
            ],
        }
        res_orders = client.parse_message(orders_raw)
        assert res_orders["event_type"] == "executionReport"
        assert len(res_orders["orders"]) == 1
        assert res_orders["orders"][0]["order_status"] == "filled"
        assert res_orders["orders"][0]["client_order_id"] == "okx_cl_test"

    def test_websocket_manager_registry(self):
        mgr = WebSocketManager()
        binance_c = mgr.create_binance_client()
        okx_c = mgr.create_okx_client()

        assert mgr.get_client("binance") is binance_c
        assert mgr.get_client("okx") is okx_c

        status = mgr.get_status()
        assert "binance" in status
        assert "okx" in status

        mgr.close_all()
        assert len(mgr._clients) == 0


# ════════════════════════════════════════════════════════════════════
# 4. Live Safety Gate & Live Mode Service Tests
# ════════════════════════════════════════════════════════════════════

class TestSafetyGate:
    """Test Live Trading Safety Gate double verification, expiration, and blocking."""

    def test_safety_gate_default_locked(self):
        gate = SafetyGate()
        with patch.dict(os.environ, {"ENABLE_LIVE_TRADING": "false", "QUANT_LIVE_TRADING_ENABLED": "false"}):
            assert gate.is_env_enabled() is False
            assert gate.is_unlocked() is False
            with pytest.raises(LiveTradingGateError) as exc:
                gate.assert_allowed()
            assert "ENABLE_LIVE_TRADING=true" in str(exc.value)

    def test_safety_gate_unlock_and_lock_cycle(self):
        gate = SafetyGate()
        with patch.dict(os.environ, {"ENABLE_LIVE_TRADING": "true"}):
            assert gate.is_env_enabled() is True
            # Locked initially
            with pytest.raises(LiveTradingGateError) as exc:
                gate.assert_allowed()
            assert "safety gate is locked" in str(exc.value)

            # Invalid unlock password
            with pytest.raises(LiveTradingGateError):
                gate.unlock("wrong_password")

            # Valid unlock
            status = gate.unlock("admin_live_safe_2026", operator="risk_lead", ttl_seconds=600)
            assert status["unlocked"] is True
            assert status["operator"] == "risk_lead"
            assert status["remaining_seconds"] > 0
            assert gate.is_unlocked() is True

            # Allowed now
            gate.assert_allowed()

            # Explicit Lock
            lock_status = gate.lock(operator="risk_lead")
            assert lock_status["unlocked"] is False
            assert gate.is_unlocked() is False
            with pytest.raises(LiveTradingGateError):
                gate.assert_allowed()

    def test_safety_gate_ttl_expiration(self):
        gate = SafetyGate()
        with patch.dict(os.environ, {"ENABLE_LIVE_TRADING": "true"}):
            gate.unlock("admin_live_safe_2026", ttl_seconds=-10)  # already expired
            assert gate.is_unlocked() is False
            with pytest.raises(LiveTradingGateError):
                gate.assert_allowed()


class TestLiveModeServiceIntegration:
    """Test LiveModeService diagnose and multi-gate assertion."""

    def test_diagnose_reports_all_gates(self):
        store = get_store()
        service = store.live_mode_service

        diag = service.diagnose(account_id="paper-main")
        assert "gates" in diag
        assert "deployment_flag" in diag["gates"]
        assert "safety_gate_unlocked" in diag["gates"]
        assert "governance_approval" in diag["gates"]
        assert "exchange_credentials" in diag["gates"]
        assert diag["authorized"] is False


# ════════════════════════════════════════════════════════════════════
# 5. Live Trading API Endpoints Tests
# ════════════════════════════════════════════════════════════════════

class TestLiveApiEndpoints:
    """Test /api/v1/live/gate endpoints and live mode interaction."""

    def test_gate_status_endpoint(self, client: TestClient):
        resp = client.get("/api/v1/live/gate/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "env_enabled" in data
        assert "unlocked" in data
        assert "remaining_seconds" in data

    def test_gate_unlock_and_lock_endpoints(self, client: TestClient):
        # Unlock with valid password
        unlock_resp = client.post("/api/v1/live/gate/unlock", json={
            "token": "admin_live_safe_2026",
            "operator": "test_operator",
            "ttl_seconds": 1800,
        })
        assert unlock_resp.status_code == 200
        data = unlock_resp.json()
        assert data["unlocked"] is True
        assert data["operator"] == "test_operator"
        assert data["remaining_seconds"] > 0

        # Check status endpoint reflects unlocked
        status_resp = client.get("/api/v1/live/gate/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["unlocked"] is True

        # Lock
        lock_resp = client.post("/api/v1/live/gate/lock", json={"operator": "test_operator"})
        assert lock_resp.status_code == 200
        assert lock_resp.json()["unlocked"] is False

    def test_gate_unlock_with_invalid_token_rejected(self, client: TestClient):
        resp = client.post("/api/v1/live/gate/unlock", json={
            "token": "invalid_bad_token",
            "operator": "attacker",
        })
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"]["code"] == "LIVE_TRADING_NOT_ALLOWED"
