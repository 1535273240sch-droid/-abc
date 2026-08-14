"""Tests for auth, RBAC, kill switch, approval, reconciliation,
market quality, SSRF protection, and pluggable strategy engines.

These tests complement ``test_trading_logic_fixes.py`` and ``test_api.py``
by covering critical paths that were previously untested.
"""

import os
import time
import pytest

from app.core.auth import (
    create_access_token,
    verify_access_token,
    authenticate,
    role_allows,
)
from app.core.config import settings
from app.core.network import validate_outbound_host, validate_safe_outbound_url
from app.core.errors import QuantError
from app.db.memory import get_store, reset_store
from app.models.domain import Position
from app.models.enums import MarketType, OrderSide
from app.services.strategy_engines import (
    StrategyEngineRegistry,
    TrendFollowingEngine,
    ArbitrageEngine,
    GridTradingEngine,
    DefaultEngine,
    default_registry,
)


# ── Auth & RBAC ─────────────────────────────────────────────────────────────


class TestAuthTokens:
    def test_create_and_verify_token(self):
        token, expires_at = create_access_token("admin", "admin")
        claims = verify_access_token(token)
        assert claims is not None
        assert claims["sub"] == "admin"
        assert claims["role"] == "admin"
        assert claims["exp"] == expires_at

    def test_verify_invalid_token_returns_none(self):
        assert verify_access_token("garbage") is None
        assert verify_access_token("q1.badbody.badsig") is None
        assert verify_access_token("") is None
        assert verify_access_token("q1..") is None

    def test_verify_tampered_token_fails(self):
        token, _ = create_access_token("admin", "admin")
        # Tamper with the body portion
        parts = token.split(".")
        parts[1] = parts[1][:-2] + "AA"
        tampered = ".".join(parts)
        assert verify_access_token(tampered) is None

    def test_authenticate_with_correct_credentials(self, monkeypatch):
        monkeypatch.setattr(settings, "auth_enabled", True)
        monkeypatch.setattr(settings, "auth_secret", "a" * 32)
        monkeypatch.setattr(settings, "auth_admin_username", "admin")
        monkeypatch.setattr(settings, "auth_admin_password", "supersecret123")
        token = authenticate("admin", "supersecret123")
        assert token is not None
        claims = verify_access_token(token)
        assert claims is not None
        assert claims["sub"] == "admin"

    def test_authenticate_with_wrong_password(self, monkeypatch):
        monkeypatch.setattr(settings, "auth_enabled", True)
        monkeypatch.setattr(settings, "auth_secret", "a" * 32)
        monkeypatch.setattr(settings, "auth_admin_username", "admin")
        monkeypatch.setattr(settings, "auth_admin_password", "supersecret123")
        assert authenticate("admin", "wrong") is None

    def test_authenticate_disabled_returns_none(self, monkeypatch):
        monkeypatch.setattr(settings, "auth_enabled", False)
        assert authenticate("admin", "anything") is None


class TestRBAC:
    def test_viewer_can_get(self):
        assert role_allows("viewer", "GET", "/api/v1/orders") is True

    def test_viewer_cannot_post(self):
        assert role_allows("viewer", "POST", "/api/v1/orders") is False

    def test_quant_can_post_orders(self):
        assert role_allows("quant", "POST", "/api/v1/orders") is True

    def test_quant_can_delete_orders_via_fallback(self):
        # The fallback allows quant to DELETE on /api/v1/orders
        assert role_allows("quant", "DELETE", "/api/v1/orders") is True

    def test_admin_can_delete(self):
        assert role_allows("admin", "DELETE", "/api/v1/orders") is True

    def test_viewer_cannot_access_audit(self):
        assert role_allows("viewer", "GET", "/api/v1/audit") is False

    def test_risk_officer_can_access_governance(self):
        assert role_allows("risk_officer", "GET", "/api/v1/governance") is True

    def test_viewer_cannot_access_control(self):
        assert role_allows("viewer", "GET", "/api/v1/control") is False

    def test_unknown_role_denied(self):
        assert role_allows("hacker", "GET", "/api/v1/orders") is False

    def test_viewer_cannot_patch(self):
        assert role_allows("viewer", "PATCH", "/api/v1/orders") is False


# ── SSRF Protection ─────────────────────────────────────────────────────────


class TestSSRFProtection:
    def test_loopback_rejected(self):
        with pytest.raises(QuantError) as exc_info:
            validate_outbound_host("127.0.0.1")
        assert exc_info.value.code == "VALIDATION_ERROR"

    def test_private_network_rejected(self):
        for addr in ("10.0.0.1", "192.168.1.1", "172.16.0.1"):
            with pytest.raises(QuantError) as exc_info:
                validate_outbound_host(addr)
            assert exc_info.value.code == "VALIDATION_ERROR"

    def test_cloud_metadata_rejected(self):
        with pytest.raises(QuantError) as exc_info:
            validate_outbound_host("169.254.169.254")
        assert exc_info.value.code == "VALIDATION_ERROR"

    def test_ipv6_loopback_rejected(self):
        with pytest.raises(QuantError) as exc_info:
            validate_outbound_host("::1")
        assert exc_info.value.code == "VALIDATION_ERROR"

    def test_public_ip_allowed(self):
        assert validate_outbound_host("8.8.8.8") == "8.8.8.8"

    def test_https_url_validation(self):
        with pytest.raises(QuantError) as exc_info:
            validate_safe_outbound_url("ftp://example.com")
        assert exc_info.value.code == "VALIDATION_ERROR"
        with pytest.raises(QuantError):
            validate_safe_outbound_url("not a url")

    def test_http_url_rejected_without_allow_flag(self):
        with pytest.raises(QuantError) as exc_info:
            validate_safe_outbound_url("http://example.com")
        assert exc_info.value.code == "VALIDATION_ERROR"

    def test_http_url_allowed_with_flag(self):
        result = validate_safe_outbound_url("http://example.com", allow_http=True)
        assert result == "http://example.com"


# ── Kill Switch ─────────────────────────────────────────────────────────────


class TestKillSwitch:
    def test_trigger_and_assert_active(self, client):
        store = get_store()
        ks = store.kill_switch_service
        assert not ks.is_active()
        ks.trigger("admin", "emergency stop")
        assert ks.is_active()
        with pytest.raises(QuantError) as exc_info:
            ks.assert_not_active("test action")
        assert exc_info.value.code == "KILL_SWITCH_ACTIVE"

    def test_trigger_blocks_order_creation(self, client):
        store = get_store()
        store.kill_switch_service.trigger("admin", "halt")
        resp = client.post(
            "/api/v1/risk/preflight",
            json={
                "account_id": "paper-main",
                "symbol": "BTCUSDT",
                "side": "buy",
                "quantity": "0.01000000",
                "price": "99900.00",
                "strategy_id": "trend-btc",
                "strategy_version": "1.0.0",
                "mode": "paper",
            },
        )
        # Preflight should still work (it's a check, not an action)
        if resp.status_code == 200:
            decision_id = resp.json()["decision_id"]
            order_resp = client.post(
                "/api/v1/orders/intents",
                json={
                    "client_order_id": "ks-test-1",
                    "account_id": "paper-main",
                    "strategy_id": "trend-btc",
                    "strategy_version": "1.0.0",
                    "symbol": "BTCUSDT",
                    "market_type": "spot",
                    "side": "buy",
                    "order_type": "limit",
                    "quantity": "0.01000000",
                    "limit_price": "99900.00",
                    "mode": "paper",
                    "risk_decision_id": decision_id,
                },
            )
            assert order_resp.status_code == 503

    def test_recover_requires_approval(self, client):
        store = get_store()
        ks = store.kill_switch_service
        ks.trigger("admin", "test")
        # Direct recovery without approval should fail
        with pytest.raises(QuantError) as exc_info:
            ks.recover("admin", "fixed", "fake-approval-id", "paper")
        assert exc_info.value.code == "NOT_FOUND"

    def test_recover_with_approval(self, client):
        store = get_store()
        ks = store.kill_switch_service
        ks.trigger("admin", "test")
        # Create and approve a kill_switch_recovery approval
        approval = store.approval_service.create(
            resource_type="kill_switch_recovery",
            resource_id="ks-test",
            requested_by="admin",
            title="Recover kill switch",
        )
        store.approval_service.decide(approval.approval_id, "approved", "admin")
        # Now recovery should work
        state = ks.recover("admin", "fixed", approval.approval_id, "paper")
        assert ks.is_active() is False


# ── Approval Workflow ───────────────────────────────────────────────────────


class TestApprovalWorkflow:
    def test_create_and_approve(self, client):
        store = get_store()
        approval = store.approval_service.create(
            resource_type="strategy_publish",
            resource_id="strat-001",
            requested_by="quant",
            title="Publish strategy v2",
        )
        assert approval.status.value == "pending"
        decided = store.approval_service.decide(
            approval.approval_id, "approved", "admin"
        )
        assert decided.status.value == "approved"
        assert decided.decided_by == "admin"

    def test_reject_approval(self, client):
        store = get_store()
        approval = store.approval_service.create(
            resource_type="risk_threshold_change",
            resource_id="rt-001",
            requested_by="quant",
            title="Lower risk threshold",
        )
        decided = store.approval_service.decide(
            approval.approval_id, "rejected", "risk_officer", "Too risky"
        )
        assert decided.status.value == "rejected"
        assert decided.reject_reason == "Too risky"

    def test_cannot_decide_twice(self, client):
        store = get_store()
        approval = store.approval_service.create(
            resource_type="strategy_publish",
            resource_id="strat-002",
            requested_by="quant",
            title="Publish v3",
        )
        store.approval_service.decide(approval.approval_id, "approved", "admin")
        with pytest.raises(QuantError) as exc_info:
            store.approval_service.decide(approval.approval_id, "rejected", "admin")
        assert exc_info.value.code == "APPROVAL_ALREADY_DECIDED"

    def test_invalid_decision_rejected(self, client):
        store = get_store()
        approval = store.approval_service.create(
            resource_type="strategy_publish",
            resource_id="strat-003",
            requested_by="quant",
            title="Publish v4",
        )
        with pytest.raises(QuantError) as exc_info:
            store.approval_service.decide(approval.approval_id, "maybe", "admin")
        assert exc_info.value.code == "VALIDATION_ERROR"

    def test_approval_not_found(self, client):
        store = get_store()
        with pytest.raises(QuantError) as exc_info:
            store.approval_service.decide("nonexistent", "approved", "admin")
        assert exc_info.value.code == "NOT_FOUND"


# ── Reconciliation ──────────────────────────────────────────────────────────


class TestReconciliation:
    def test_reconciliation_runs_and_returns_log(self, client):
        store = get_store()
        log = store.reconciliation_service.run("paper-main")
        # Seeded state has a position but no orders → discrepancy is expected
        assert log.status.value in ("consistent", "discrepancy")
        assert log.summary["total_positions"] >= 0
        assert log.summary["total_orders"] >= 0

    def test_discrepancy_detected(self, client):
        store = get_store()
        # Inject an orphan position that has no matching order
        orphan = Position(
            position_id="pos-orphan-1",
            account_id="paper-main",
            symbol="XYZUSDT",
            market_type=MarketType.SPOT,
            side=OrderSide.BUY,
            quantity="0.50000000",
            entry_price="100.00",
            current_price="100.00",
        )
        store.positions[orphan.position_id] = orphan
        log = store.reconciliation_service.run("paper-main")
        assert log.status.value == "discrepancy"

    def test_resolution_recorded(self, client):
        store = get_store()
        log = store.reconciliation_service.run("paper-main")
        resolution = store.reconciliation_service.resolve(
            reconciliation_id=log.reconciliation_id,
            decision="acknowledged",
            reason="Known seed position mismatch",
            actor="admin",
            mode="paper",
        )
        assert resolution.decision.value == "acknowledged"
        assert resolution.actor == "admin"

    def test_resolution_idempotency(self, client):
        store = get_store()
        log = store.reconciliation_service.run("paper-main")
        r1 = store.reconciliation_service.resolve(
            reconciliation_id=log.reconciliation_id,
            decision="acknowledged",
            reason="test",
            actor="admin",
            mode="paper",
            idempotency_key="resolve-idem-1",
        )
        r2 = store.reconciliation_service.resolve(
            reconciliation_id=log.reconciliation_id,
            decision="acknowledged",
            reason="test",
            actor="admin",
            mode="paper",
            idempotency_key="resolve-idem-1",
        )
        assert r1.resolution_id == r2.resolution_id


# ── Market Quality ──────────────────────────────────────────────────────────


class TestMarketQuality:
    def test_quality_healthy_with_seeded_tickers(self, client):
        store = get_store()
        quality = store.market_service.quality()
        assert quality["status"] == "healthy"
        assert quality["usable"] is True
        assert len(quality["issues"]) == 0

    def test_quality_degraded_on_missing_ticker(self, client):
        store = get_store()
        del store.tickers["BTCUSDT"]
        quality = store.market_service.quality()
        assert quality["status"] == "degraded"
        assert any(i["code"] == "MISSING_TICKERS" for i in quality["issues"])

    def test_quality_degraded_on_invalid_price(self, client):
        store = get_store()
        store.tickers["BTCUSDT"].last_price = "0"
        quality = store.market_service.quality()
        assert quality["status"] == "degraded"
        assert any(i["code"] == "INVALID_PRICES" for i in quality["issues"])

    def test_quality_degraded_on_crossed_book(self, client):
        store = get_store()
        store.tickers["BTCUSDT"].ask_price = "1.00"
        store.tickers["BTCUSDT"].bid_price = "2.00"
        quality = store.market_service.quality()
        assert quality["status"] == "degraded"
        assert any(i["code"] == "CROSSED_BOOK" for i in quality["issues"])

    def test_circuit_breakers_listed(self, client):
        store = get_store()
        breakers = store.risk_service.circuit_breakers()
        assert len(breakers) == 3
        ids = [b["id"] for b in breakers]
        assert "kill_switch" in ids
        assert "market_quality" in ids
        assert "public_feed" in ids


# ── Pluggable Strategy Engines ──────────────────────────────────────────────


class TestStrategyEngines:
    def test_registry_returns_correct_engine(self):
        reg = default_registry()
        assert isinstance(reg.get("trend"), TrendFollowingEngine)
        assert isinstance(reg.get("arbitrage"), ArbitrageEngine)
        assert isinstance(reg.get("grid"), GridTradingEngine)

    def test_registry_fallback_for_unknown_kind(self):
        reg = default_registry()
        engine = reg.get("unknown_kind")
        assert isinstance(engine, DefaultEngine)

    def test_custom_engine_registration(self):
        reg = StrategyEngineRegistry()
        custom = DefaultEngine()
        reg.register("custom", custom)
        assert reg.get("custom") is custom
        assert "custom" in reg.registered_kinds

    def test_trend_engine_generates_buy_on_positive_change(self, client):
        store = get_store()
        strategy = store.strategy_service.get("trend-btc")
        quality = store.market_service.quality()
        engine = TrendFollowingEngine()
        signals = engine.generate_signals(strategy, quality, store.tickers)
        # Seeded BTCUSDT change is +2.34, so trend should generate buy
        buy_signals = [s for s in signals if s["action"] == "buy"]
        assert len(buy_signals) == 1
        assert buy_signals[0]["signal"] == "positive_24h_trend"

    def test_trend_engine_hold_on_negative_change(self, client):
        store = get_store()
        strategy = store.strategy_service.get("trend-btc")
        # Set negative change
        store.tickers["BTCUSDT"].change_24h = "-2.50"
        quality = store.market_service.quality()
        engine = TrendFollowingEngine()
        signals = engine.generate_signals(strategy, quality, store.tickers)
        hold_signals = [s for s in signals if s["action"] == "hold"]
        assert len(hold_signals) == 1
        assert hold_signals[0]["status"] == "no_signal"

    def test_arbitrage_engine_always_hold(self, client):
        store = get_store()
        strategy = store.strategy_service.get("arb-eth")
        quality = store.market_service.quality()
        engine = ArbitrageEngine()
        signals = engine.generate_signals(strategy, quality, store.tickers)
        assert len(signals) == 1
        assert signals[0]["action"] == "hold"
        assert signals[0]["reason"] == "cross_exchange_spread_unavailable"

    def test_engine_blocked_on_missing_ticker(self, client):
        store = get_store()
        strategy = store.strategy_service.get("trend-btc")
        # Remove the ticker
        del store.tickers["BTCUSDT"]
        quality = store.market_service.quality()
        engine = TrendFollowingEngine()
        signals = engine.generate_signals(strategy, quality, {})
        assert len(signals) == 1
        assert signals[0]["status"] == "blocked"
        assert signals[0]["reason"] == "ticker_missing"

    def test_runtime_uses_registry(self, client):
        store = get_store()
        # Verify the runtime service has a registry
        assert hasattr(store.strategy_runtime_service, "_engine_registry")
        reg = store.strategy_runtime_service._engine_registry
        assert "trend" in reg.registered_kinds
        assert "arbitrage" in reg.registered_kinds
        assert "grid" in reg.registered_kinds


# ── Error Code Consistency ──────────────────────────────────────────────────


class TestErrorCodeConsistency:
    def test_risk_preflight_uses_unified_error_code(self, client):
        resp = client.post(
            "/api/v1/risk/preflight",
            json={
                "account_id": "paper-main",
                "symbol": "BTCUSDT",
                "side": "buy",
                "quantity": "NaN",
                "price": "99900.00",
                "strategy_id": "trend-btc",
                "strategy_version": "1.0.0",
                "mode": "paper",
            },
        )
        assert resp.status_code == 400
        code = resp.json()["error"]["code"]
        assert code == "VALIDATION_ERROR"

    def test_risk_preflight_negative_price_uses_unified_code(self, client):
        resp = client.post(
            "/api/v1/risk/preflight",
            json={
                "account_id": "paper-main",
                "symbol": "BTCUSDT",
                "side": "buy",
                "quantity": "0.01000000",
                "price": "-1.0",
                "strategy_id": "trend-btc",
                "strategy_version": "1.0.0",
                "mode": "paper",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
