# Adversarial Stress Testing & Edge-Case Boundary Verification Suite
# Authored by Adversarial Challenger 1

import base64
import hashlib
import hmac
import json
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.adapters.live_exchange_adapters import BinanceLiveAdapter, OkxLiveAdapter, LiveAdapterError
from app.core.auth import (
    create_access_token,
    create_refresh_token,
    create_user,
    reset_users,
    verify_token,
    verify_access_token,
    require_role,
    require_permission,
    hash_password,
    verify_password,
    role_allows,
    ROLE_PERMISSIONS,
    ROLE_PERMISSIONS_MAP,
)
from app.core.config import settings
from app.core.errors import QuantError
from app.events.bus import now_utc
from app.main import app
from app.models.domain import Approval, ApprovalResourceType, ApprovalStatus
from app.services.alert_notification_service import (
    AlertNotificationService,
    truncate_text,
    MAX_MESSAGE_LENGTH,
)
from app.services.backtest_engine import (
    BacktestEngine,
    BacktestPosition,
    BacktestTrade,
    FeeModel,
    SlippageModel,
)
from app.services.live_mode_service import LiveModeService, SafetyGate, LiveTradingGateError
from app.strategies.base import Strategy, StrategyMeta, ParamSpec
from app.strategies.library.dual_ma import DualMaStrategy
from app.strategies.signal import Bar, Signal, SignalType


@pytest.fixture(autouse=True)
def setup_auth_environment():
    """Ensure clean auth environment and reset in-memory user registry for each test."""
    reset_users()
    orig_enabled = settings.auth_enabled
    orig_secret = settings.auth_secret
    orig_admin_user = settings.auth_admin_username
    orig_admin_pass = settings.auth_admin_password
    orig_ttl = settings.auth_token_ttl_seconds

    settings.auth_enabled = True
    settings.auth_secret = "test_auth_secret_key_32_characters_long_12345"
    settings.auth_admin_username = "admin"
    settings.auth_admin_password = "AdminSuperSecretPassword123!"
    settings.auth_token_ttl_seconds = 3600

    yield

    reset_users()
    settings.auth_enabled = orig_enabled
    settings.auth_secret = orig_secret
    settings.auth_admin_username = orig_admin_user
    settings.auth_admin_password = orig_admin_pass
    settings.auth_token_ttl_seconds = orig_ttl


# =====================================================================
# 1. QUANTITATIVE METRICS & SLIPPAGE ADVERSARIAL TESTS
# =====================================================================

class TestQuantitativeMetricsAdversarial:
    """Stress testing quant metrics on zero-volatility, division by zero, bankruptcy and extreme distributions."""

    def _create_engine(self, bars, initial_capital="100000", fee_model="zero", slippage_model="none"):
        return BacktestEngine(
            bars=bars,
            strategy_cls=DualMaStrategy,
            params={"fast_period": 5, "slow_period": 10},
            initial_capital=initial_capital,
            fee_model=fee_model,
            slippage_model=slippage_model,
        )

    def test_zero_trades_zero_volatility_metrics(self):
        """Zero trades and completely flat equity curve must return safe zeroes, no NaN/Inf/ZeroDivision."""
        bars = [
            Bar(open_time=1000 * 3600 * i, open=Decimal("100"), high=Decimal("100"), low=Decimal("100"), close=Decimal("100"), volume=Decimal("10"), symbol="BTC/USDT")
            for i in range(10)
        ]
        engine = self._create_engine(bars, initial_capital="100000")
        equity_curve = [(1000 * 3600 * i, Decimal("100000")) for i in range(10)]
        
        metrics = engine._metrics(trades=[], equity_curve=equity_curve, final_equity=Decimal("100000"), max_dd=Decimal("0"))
        
        assert metrics["net_profit"] == "0.00"
        assert metrics["final_equity"] == "100000.00"
        assert metrics["total_return_pct"] == "0.00%"
        assert metrics["cagr"] == 0.0
        assert metrics["sharpe_ratio"] == "0.00"
        assert metrics["sortino_ratio"] == 0.0
        assert metrics["calmar_ratio"] == 0.0
        assert metrics["max_drawdown"] == "-0.0000%"
        assert metrics["drawdown_duration"] == 0
        assert metrics["win_rate"] == "0.00%"
        assert metrics["profit_factor"] == "0.00"
        assert metrics["payoff_ratio"] == 0.0
        assert metrics["total_trades"] == 0

    def test_bankruptcy_and_negative_equity_boundary(self):
        """Catastrophic loss leading to negative equity (liquidation/loss > 100%) must be bounded."""
        bars = [
            Bar(open_time=1000 * 3600 * i, open=Decimal("100"), high=Decimal("100"), low=Decimal("100"), close=Decimal("100"), volume=Decimal("10"), symbol="BTC/USDT")
            for i in range(10)
        ]
        engine = self._create_engine(bars, initial_capital="100000")
        # Equity plunges below zero to -20000
        equity_curve = [
            (0, Decimal("100000")),
            (1000 * 3600, Decimal("50000")),
            (2000 * 3600, Decimal("0")),
            (3000 * 3600, Decimal("-20000")),
        ]
        trades = [
            BacktestTrade(
                entry_time=0, exit_time=3000 * 3600, symbol="BTC/USDT", side="buy",
                quantity=Decimal("10"), entry_price=Decimal("100"), exit_price=Decimal("0"),
                gross_pnl=Decimal("-120000"), fee_paid=Decimal("0"), net_pnl=Decimal("-120000"),
                return_pct=Decimal("-1.2"), exit_reason="liquidation",
            )
        ]
        metrics = engine._metrics(trades=trades, equity_curve=equity_curve, final_equity=Decimal("-20000"), max_dd=Decimal("1.2"))
        
        assert Decimal(metrics["net_profit"]) == Decimal("-120000.00")
        assert metrics["cagr"] == -1.0
        assert metrics["win_rate"] == "0.00%"
        assert metrics["profit_factor"] == "0.00"
        # max_drawdown bounded to max 1.0 (100%)
        assert metrics["max_drawdown"] == "-100.0000%"

    def test_all_losing_trades_boundary(self):
        """When all trades lose, win_rate and profit_factor must be zero without division error."""
        one_day = 86400000
        bars = [
            Bar(open_time=one_day * i, open=Decimal("100"), high=Decimal("100"), low=Decimal("100"), close=Decimal("100"), volume=Decimal("10"), symbol="BTC/USDT")
            for i in range(10)
        ]
        engine = self._create_engine(bars, initial_capital="100000")
        trades = [
            BacktestTrade(
                entry_time=0, exit_time=one_day * 2, symbol="BTC/USDT", side="buy",
                quantity=Decimal("1"), entry_price=Decimal("100"), exit_price=Decimal("90"),
                gross_pnl=Decimal("-10"), fee_paid=Decimal("0"), net_pnl=Decimal("-10"),
                return_pct=Decimal("-0.1"), exit_reason="stop_loss",
            ),
            BacktestTrade(
                entry_time=one_day * 2, exit_time=one_day * 4, symbol="BTC/USDT", side="buy",
                quantity=Decimal("1"), entry_price=Decimal("100"), exit_price=Decimal("80"),
                gross_pnl=Decimal("-20"), fee_paid=Decimal("0"), net_pnl=Decimal("-20"),
                return_pct=Decimal("-0.2"), exit_reason="stop_loss",
            ),
        ]
        equity_curve = [(0, Decimal("100000")), (one_day * 2, Decimal("99990")), (one_day * 4, Decimal("99970"))]
        metrics = engine._metrics(trades=trades, equity_curve=equity_curve, final_equity=Decimal("99970"), max_dd=Decimal("0.0003"))

        assert metrics["win_rate"] == "0.00%"
        assert metrics["profit_factor"] == "0.00"
        assert metrics["payoff_ratio"] == 0.0
        assert metrics["winning_trades"] == 0
        assert metrics["losing_trades"] == 2

    def test_all_winning_trades_infinite_ratio_cap(self):
        """When all trades win (gross_loss = 0), profit_factor and payoff_ratio must safely cap at 999.0."""
        one_day = 86400000
        bars = [
            Bar(open_time=one_day * i, open=Decimal("100"), high=Decimal("100"), low=Decimal("100"), close=Decimal("100"), volume=Decimal("10"), symbol="BTC/USDT")
            for i in range(365)
        ]
        engine = self._create_engine(bars, initial_capital="100000")
        trades = [
            BacktestTrade(
                entry_time=0, exit_time=one_day * 100, symbol="BTC/USDT", side="buy",
                quantity=Decimal("1"), entry_price=Decimal("100"), exit_price=Decimal("120"),
                gross_pnl=Decimal("20000"), fee_paid=Decimal("0"), net_pnl=Decimal("20000"),
                return_pct=Decimal("0.2"), exit_reason="take_profit",
            ),
            BacktestTrade(
                entry_time=one_day * 100, exit_time=one_day * 200, symbol="BTC/USDT", side="buy",
                quantity=Decimal("1"), entry_price=Decimal("100"), exit_price=Decimal("110"),
                gross_pnl=Decimal("10000"), fee_paid=Decimal("0"), net_pnl=Decimal("10000"),
                return_pct=Decimal("0.1"), exit_reason="take_profit",
            ),
        ]
        equity_curve = [(0, Decimal("100000")), (one_day * 100, Decimal("120000")), (one_day * 365, Decimal("130000"))]
        metrics = engine._metrics(trades=trades, equity_curve=equity_curve, final_equity=Decimal("130000"), max_dd=Decimal("0"))

        assert metrics["win_rate"] == "100.00%"
        assert metrics["profit_factor"] == "999.00"
        assert metrics["payoff_ratio"] == 999.0
        assert metrics["sortino_ratio"] == 999.0
        assert metrics["calmar_ratio"] == 999.0
        assert metrics["cagr"] > 0.0

    def test_atr_dynamic_slippage_extreme_volatility_and_non_negative_clamp(self):
        """ATR dynamic slippage must handle extreme volatility without resulting in negative prices."""
        bar = Bar(open_time=1000, open=Decimal("100"), high=Decimal("500"), low=Decimal("50"), close=Decimal("100"), volume=Decimal("1000"), symbol="BTC/USDT")
        
        # Test extreme ATR mult = 5.0 on price 100 with ATR 300 -> slip = 1500
        slip_model = SlippageModel(mode="dynamic", atr_mult=Decimal("5.0"))
        
        # Buy price slips upward: 100 + 1500 = 1600
        buy_price = slip_model.apply(side="buy", price=Decimal("100"), bar=bar, atr=Decimal("300"))
        assert buy_price == Decimal("1600.00000000")
        
        # Sell price slips downward: 100 - 1500 = -1400 -> clamped to 0.00000001
        sell_price = slip_model.apply(side="sell", price=Decimal("100"), bar=bar, atr=Decimal("300"))
        assert sell_price == Decimal("0.00000001")
        assert sell_price > Decimal("0")

    def test_fixed_and_percentage_slippage_extreme_bounds(self):
        """Fixed and percentage slippage models must never allow price to drop <= 0."""
        bar = Bar(open_time=1000, open=Decimal("10"), high=Decimal("12"), low=Decimal("8"), close=Decimal("10"), volume=Decimal("100"), symbol="BTC/USDT")
        
        # Fixed amount larger than price (price=10, fixed=50)
        fixed_slip = SlippageModel(mode="fixed_price", fixed_amount=Decimal("50"))
        assert fixed_slip.apply("buy", Decimal("10"), bar) == Decimal("60")
        assert fixed_slip.apply("sell", Decimal("10"), bar) == Decimal("0.00000001")

        # Percentage rate 150% (pct_rate=1.5)
        pct_slip = SlippageModel(mode="percentage", pct_rate=Decimal("1.5"))
        assert pct_slip.apply("buy", Decimal("10"), bar) == Decimal("25.0")
        assert pct_slip.apply("sell", Decimal("10"), bar) == Decimal("0.00000001")

    def test_fee_model_extreme_rates_and_funding(self):
        """FeeModel must accurately compute taker/maker fee and perpetual funding payments."""
        fee_model = FeeModel(
            maker_rate=Decimal("0.001"),
            taker_rate=Decimal("0.002"),
            funding_rate=Decimal("-0.0005"), # Negative funding: longs receive, shorts pay
        )
        
        # Taker fee for 10 BTC at 50,000 USDT = 500,000 * 0.002 = 1,000 USDT
        fee = fee_model.calculate(qty=Decimal("10"), price=Decimal("50000"), is_maker=False)
        assert fee == Decimal("1000.00000000")
        
        # Long position funding: notional * funding_rate = 500,000 * -0.0005 = -250 (income)
        long_funding = fee_model.funding_payment(quantity=Decimal("10"), price=Decimal("50000"), is_long=True)
        assert long_funding == Decimal("-250.00000000")
        
        # Short position funding: -notional * funding_rate = +250 (cost)
        short_funding = fee_model.funding_payment(quantity=Decimal("10"), price=Decimal("50000"), is_long=False)
        assert short_funding == Decimal("250.00000000")


# =====================================================================
# 2. EXCHANGE SIGNATURE & LIVE SAFETY GATE ADVERSARIAL TESTS
# =====================================================================

class TestExchangeSigningAndSafetyGateAdversarial:
    """Stress testing exchange signatures, missing credentials, timestamp replay, and multi-tier live gate."""

    def test_binance_signing_tamper_detection(self):
        """Binance HMAC-SHA256 signature must change if any parameter is altered."""
        adapter = BinanceLiveAdapter(
            credentials={"api_key": "test_binance_key", "api_secret": "test_binance_secret_super_secure_123"},
            base_url="https://api.binance.com",
        )
        ts = 1700000000000
        sign_1 = adapter.sign("POST", "/api/v3/order", params={"symbol": "BTCUSDT", "side": "BUY", "quantity": "1.0"}, timestamp=ts)
        
        # Tamper quantity from 1.0 to 10.0
        sign_tampered = adapter.sign("POST", "/api/v3/order", params={"symbol": "BTCUSDT", "side": "BUY", "quantity": "10.0"}, timestamp=ts)
        
        assert sign_1["signature"] != sign_tampered["signature"]
        assert sign_1["headers"]["X-MBX-APIKEY"] == "test_binance_key"
        
        # Re-verify manual HMAC calculation
        expected_sig = hmac.new(
            b"test_binance_secret_super_secure_123",
            urllib.parse.urlencode({"symbol": "BTCUSDT", "side": "BUY", "quantity": "1.0", "timestamp": ts, "recvWindow": 5000}).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert sign_1["signature"] == expected_sig

    def test_binance_missing_credentials_raises_error(self):
        """Missing api_key or secret must be rejected immediately."""
        adapter = BinanceLiveAdapter(credentials={"api_key": "", "api_secret": ""}, base_url="https://api.binance.com")
        with pytest.raises(LiveAdapterError, match="missing api_key/api_secret"):
            adapter.sign("GET", "/api/v3/account")

    def test_okx_signing_tamper_and_passphrase_requirement(self):
        """OKX v5 signature requires passphrase and binds timestamp + method + path + body."""
        adapter = OkxLiveAdapter(
            credentials={"api_key": "okx_key_1", "api_secret": "okx_secret_1", "passphrase": "my_passphrase_999"},
            base_url="https://www.okx.com",
        )
        ts = "2026-08-17T18:00:00.000Z"
        body = {"instId": "BTC-USDT-SWAP", "tdMode": "cross", "side": "buy", "sz": "1"}
        headers = adapter.sign("POST", "/api/v5/trade/order", body=body, timestamp=ts)
        
        assert headers["OK-ACCESS-KEY"] == "okx_key_1"
        assert headers["OK-ACCESS-PASSPHRASE"] == "my_passphrase_999"
        assert headers["OK-ACCESS-TIMESTAMP"] == ts
        
        # Manual verification
        body_json = json.dumps(body, separators=(",", ":"))
        prehash = f"{ts}POST/api/v5/trade/order{body_json}"
        expected_sign = base64.b64encode(
            hmac.new(b"okx_secret_1", prehash.encode("utf-8"), hashlib.sha256).digest()
        ).decode("utf-8")
        assert headers["OK-ACCESS-SIGN"] == expected_sign

    def test_okx_ws_auth_params_generation(self):
        """OKX WebSocket login arguments format."""
        adapter = OkxLiveAdapter(
            credentials={"api_key": "okx_key_1", "api_secret": "okx_secret_1", "passphrase": "my_passphrase_999"},
            base_url="https://www.okx.com",
        )
        ts = "1700000000"
        auth_args = adapter.get_ws_auth_params(timestamp=ts)
        assert auth_args["apiKey"] == "okx_key_1"
        assert auth_args["passphrase"] == "my_passphrase_999"
        assert auth_args["timestamp"] == ts
        assert "sign" in auth_args

    def test_okx_missing_passphrase_raises(self):
        """OKX missing passphrase must be refused."""
        adapter = OkxLiveAdapter(credentials={"api_key": "okx_key", "api_secret": "okx_secret", "passphrase": ""}, base_url="https://www.okx.com")
        with pytest.raises(LiveAdapterError, match="missing passphrase"):
            adapter.sign("GET", "/api/v5/account/balance")

    def test_live_safety_gate_penetration_tests(self):
        """Adversarial attempts to bypass live trading safety gate without authorization."""
        gate = SafetyGate()
        
        # 1. Default state: locked & env disabled -> assert_allowed fails
        assert not gate.is_unlocked()
        with pytest.raises(LiveTradingGateError, match="disabled by environment flag"):
            gate.assert_allowed()
            
        # 2. Enable env flag, but gate locked with invalid token -> fails
        with patch.object(gate, "is_env_enabled", return_value=True):
            with pytest.raises(LiveTradingGateError, match="safety gate is locked"):
                gate.assert_allowed(token="wrong_token_123")
                
            # 3. Unlock gate with correct token (DEFAULT_PASSWORD)
            unlock_res = gate.unlock(token=SafetyGate.DEFAULT_PASSWORD, operator="admin", ttl_seconds=2)
            assert unlock_res["unlocked"] is True
            assert gate.is_unlocked() is True
            # Now allowed
            gate.assert_allowed()
            
            # 4. Wait for TTL expiration
            time.sleep(2.1)
            assert gate.is_unlocked() is False
            with pytest.raises(LiveTradingGateError, match="safety gate is locked"):
                gate.assert_allowed()

    def test_live_mode_service_four_gate_diagnosis_blocks_unauthorized(self):
        """LiveModeService requires all 4 gates (env, unlock, governance approval, credentials)."""
        mock_store = MagicMock()
        mock_store.approvals = {}
        mock_store.exchange_connections = {}
        service = LiveModeService(mock_store)
        
        # Diagnosis reports all missing gates
        diag = service.diagnose(account_id="live-fund-1", exchange="binance")
        assert diag["authorized"] is False
        assert len(diag["blocking_gates"]) >= 3
        
        with pytest.raises(LiveTradingGateError):
            service.assert_live_allowed(account_id="live-fund-1", exchange="binance")

    def test_live_mode_service_revoke_authorization(self):
        """Revoking authorization must immediately invalidate active live approvals."""
        mock_store = MagicMock()
        mock_approval = MagicMock()
        mock_approval.resource_type = ApprovalResourceType.LIVE_SWITCH
        mock_approval.resource_id = "fund-01"
        mock_approval.status = ApprovalStatus.APPROVED
        mock_approval.is_expired.return_value = False

        mock_store.approvals = {"app-01": mock_approval}
        service = LiveModeService(mock_store)

        rev_res = service.revoke_authorization(account_id="fund-01", operator="risk_officer")
        assert rev_res["revoked_approvals"] == 1
        assert mock_approval.status == ApprovalStatus.EXPIRED


# =====================================================================
# 3. AUTHENTICATION & RBAC ADVERSARIAL TESTS
# =====================================================================

class TestAuthAndRbacAdversarial:
    """Stress testing JWT forgery, algorithm tampering, expired tokens, and RBAC permission isolation."""

    @pytest.fixture(autouse=True)
    def setup_auth(self, monkeypatch):
        monkeypatch.setattr(settings, "auth_enabled", True)
        monkeypatch.setattr(settings, "auth_secret", "test_auth_secret_key_32_characters_long_12345")

    def test_jwt_alg_none_attack_rejection(self):
        """Token with alg: none must be rejected by verify_token."""
        header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(json.dumps({
            "sub": "attacker",
            "role": "admin",
            "roles": ["admin"],
            "exp": int(time.time()) + 3600,
        }).encode()).decode().rstrip("=")
        token = f"{header}.{payload}."
        
        verified = verify_token(token)
        assert verified is None, "Vulnerability: alg=none token was accepted!"

    def test_jwt_payload_tamper_rejection(self):
        """Modifying payload claims without valid signature must fail verification."""
        token_res = create_access_token("trader_bob", role="trader")
        token = str(token_res)
        parts = token.split(".")
        assert len(parts) == 3
        
        # Decode payload, elevate role to admin, re-encode with same signature
        raw_payload = json.loads(base64.urlsafe_b64decode(parts[1] + "==").decode())
        raw_payload["role"] = "admin"
        raw_payload["roles"] = ["admin"]
        tampered_payload = base64.urlsafe_b64encode(json.dumps(raw_payload).encode()).decode().rstrip("=")
        tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"
        
        assert verify_token(tampered_token) is None, "Vulnerability: tampered payload was accepted!"

    def test_jwt_expired_token_rejection(self):
        """Token with exp in the past must be rejected."""
        token_res = create_access_token("trader_bob", role="trader", expires_delta=timedelta(seconds=-10))
        assert verify_token(str(token_res)) is None

    def test_jwt_wrong_secret_rejection(self):
        """Token signed by different secret must be rejected."""
        # Create token manually with fake secret
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(json.dumps({
            "sub": "admin", "role": "admin", "exp": int(time.time()) + 3600
        }).encode()).decode().rstrip("=")
        fake_sig = base64.urlsafe_b64encode(
            hmac.new(b"attacker_secret", f"{header}.{payload}".encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")
        fake_token = f"{header}.{payload}.{fake_sig}"
        
        assert verify_token(fake_token) is None

    def test_jwt_missing_sub_rejected(self):
        """JWT missing 'sub' subject claim must fail verification."""
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(json.dumps({
            "role": "admin", "exp": int(time.time()) + 3600
        }).encode()).decode().rstrip("=")
        sig = base64.urlsafe_b64encode(
            hmac.new(settings.auth_secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")
        token = f"{header}.{payload}.{sig}"
        assert verify_token(token) is None

    def test_jwt_refresh_token_cannot_be_used_as_access_token_in_strict_mode(self):
        """Refresh token has type='refresh' and cannot be accepted when token_type='access' is required."""
        ref_token = create_refresh_token("trader_bob", role="trader")
        assert verify_token(str(ref_token), token_type="access") is None
        assert verify_token(str(ref_token), token_type="refresh") is not None

    def test_rbac_matrix_and_role_allows_enforcement(self):
        """Role permission matrix must strictly restrict sensitive operations."""
        # 1. Trader cannot mutate control/governance or trigger kill-switch
        assert role_allows("trader", "POST", "/api/v1/control") is False
        assert role_allows("trader", "POST", "/api/v1/governance") is False
        assert role_allows("trader", "POST", "/api/v1/orders") is True

        # 2. Auditor cannot write/post
        assert role_allows("auditor", "GET", "/api/v1/audit") is True
        assert role_allows("auditor", "POST", "/api/v1/orders") is False
        assert role_allows("auditor", "DELETE", "/api/v1/orders") is False

        # 3. Viewer has only read-only non-sensitive access
        assert role_allows("viewer", "GET", "/api/v1/orders") is True
        assert role_allows("viewer", "POST", "/api/v1/orders") is False
        assert role_allows("viewer", "GET", "/api/v1/governance") is False
        assert role_allows("viewer", "GET", "/api/v1/control") is False

    def test_rbac_trader_cannot_call_governance_api(self):
        """Trader token rejected with 403 on governance routes."""
        client = TestClient(app)
        token_res = create_access_token("trader_user", role="trader")
        headers = {"Authorization": f"Bearer {str(token_res)}"}
        
        resp = client.get("/api/v1/governance/approvals", headers=headers)
        assert resp.status_code == 403, f"Expected 403 Forbidden for trader on governance, got {resp.status_code}"

    def test_rbac_auditor_cannot_execute_writes(self):
        """Auditor role cannot place orders or mutate state."""
        client = TestClient(app)
        token_res = create_access_token("auditor_user", role="auditor")
        headers = {"Authorization": f"Bearer {str(token_res)}"}
        
        # Auditor attempting order placement
        order_payload = {
            "symbol": "BTC/USDT",
            "side": "buy",
            "order_type": "limit",
            "quantity": 0.01,
            "price": 50000.0,
        }
        resp = client.post("/api/v1/orders", headers=headers, json=order_payload)
        assert resp.status_code == 403, f"Expected 403 Forbidden for auditor creating order, got {resp.status_code}"

    def test_password_hashing_and_verification(self):
        """Salted PBKDF2-HMAC-SHA256 password hashing."""
        pwd = "MySuperSecretPassword@2026!#$%"
        hashed = hash_password(pwd)
        assert hashed.startswith("pbkdf2_sha256$")
        assert verify_password(pwd, hashed) is True
        assert verify_password("WrongPassword123", hashed) is False
        assert verify_password("", hashed) is False


# =====================================================================
# 4. WEBHOOK RESILIENCE & BACKOFF ADVERSARIAL TESTS
# =====================================================================

class TestAlertWebhooksAdversarial:
    """Stress testing Webhook payload generation, message truncation (>4096 chars), and retry backoff."""

    def test_webhook_message_truncation_on_massive_payload(self):
        """Huge payload exceeding 4096 characters must be cleanly truncated without crashing or memory explosion."""
        massive_text = "A" * 100000  # 100KB of text
        truncated = truncate_text(massive_text, max_length=4096)
        assert len(truncated) <= 4096
        assert truncated.endswith("...(truncated)")

    def test_dingtalk_signature_exact_conformance(self):
        """DingTalk timestamp + HMAC-SHA256 signature verification."""
        service = AlertNotificationService(store=None)
        secret = "SEC1234567890abcdef"
        ts = 1700000000000
        
        ts_res, sign = service.calculate_dingtalk_sign(secret, timestamp=ts)
        assert ts_res == str(ts)
        
        # Calculate reference sign
        string_to_sign = f"{ts}\n{secret}"
        expected_hmac = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
        expected_sign = urllib.parse.quote_plus(base64.b64encode(expected_hmac).decode("utf-8"))
        assert sign == expected_sign

    def test_webhook_exponential_backoff_on_429_and_500(self):
        """Service must retry up to 3 times on HTTP 429 / 5xx with backoff sleep intervals."""
        service = AlertNotificationService(store=None, timeout=2.0)
        
        mock_sleeps = []
        service._sleep_func = lambda s: mock_sleeps.append(s)
        
        # Simulate 429 Too Many Requests HTTPError
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="https://oapi.dingtalk.com/robot/send",
                code=429,
                msg="Too Many Requests",
                hdrs={},
                fp=MagicMock(read=lambda: b"rate limit exceeded"),
            )
            
            status = service._send_http_with_backoff(
                url="https://oapi.dingtalk.com/robot/send",
                payload_data={"msgtype": "text"},
                channel_name="dingtalk",
                backoff_factors=(0.1, 0.2, 0.4),
            )
            
            assert status == "http_429"
            assert mock_urlopen.call_count == 3
            assert mock_sleeps == [0.1, 0.2]  # Slept twice between the 3 attempts

    def test_webhook_network_connection_failure_handled_gracefully(self):
        """Network connection refusal must be caught and logged without raising unhandled exception."""
        service = AlertNotificationService(store=None, timeout=1.0)
        service._sleep_func = lambda s: None
        
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            status = service._send_http_with_backoff(
                url="https://invalid.webhook.destination/test",
                payload_data={"msgtype": "text"},
                channel_name="wechat_work",
                backoff_factors=(0.01, 0.02, 0.04),
            )
            assert "error:" in status or "Connection refused" in status
            assert service.failed_count == 1

    def test_webhook_formatting_with_none_and_unicode(self):
        """Ensure Feishu and WeChat Work payload builders do not crash with complex metadata or None."""
        service = AlertNotificationService(store=None)
        record = {
            "alert_id": "alt-test-01",
            "title": "风险预警: 熔断触发",
            "message": "杠杆率超限 (15.5x > 10.0x)\n包含特殊字符: alert(1) and special chars",
            "severity": "critical",
            "source": "risk_engine",
            "created_at": "2026-08-17T18:00:00Z",
            "details": {
                "none_val": None,
                "nested": {"k": "v", "list": [1, 2, 3]},
                "unicode": "币安/OKX 交易所连接断开",
            },
        }
        
        wechat_payload = service.build_wechat_work_payload(record)
        assert wechat_payload["msgtype"] == "markdown"
        assert "content" in wechat_payload["markdown"]
        assert len(wechat_payload["markdown"]["content"]) <= MAX_MESSAGE_LENGTH
        
        feishu_payload = service.build_feishu_payload(record)
        assert feishu_payload["msg_type"] == "post"
        assert "post" in feishu_payload["content"]
        
        dingtalk_payload = service.build_dingtalk_payload(record)
        assert dingtalk_payload["msgtype"] == "markdown"
        assert len(dingtalk_payload["markdown"]["text"]) <= MAX_MESSAGE_LENGTH
