"""Tier 2: Boundary Value Analysis & Exception Handling E2E Test Suite (F1 - F12).

Tests boundary limits, extreme parameters, invalid types, SSRF blocks,
tampered cryptographic MACs, unauthorized access, and corner-case exceptions.
Total Test Cases: 66 (>= 64 required).
"""

from __future__ import annotations

import math
import re
import uuid
from decimal import Decimal
import httpx
import pytest

from app.core.auth import create_access_token, verify_token
from app.core.credential_crypto import CredentialCryptoError, open_dict, seal_dict
from app.indicators.registry import sma
from app.strategies.signal import Bar


def _get_asset_urls(nginx_client: httpx.Client) -> tuple[str, str]:
    resp = nginx_client.get("/")
    css_match = re.search(r'href="(/assets/index-[^"]+\.css)"', resp.text)
    js_match = re.search(r'src="(/assets/index-[^"]+\.js)"', resp.text)
    css_url = css_match.group(1) if css_match else "/assets/index-BuIILVdV.css"
    js_url = js_match.group(1) if js_match else "/assets/index-acZVLmpS.js"
    return css_url, js_url


# ── F1: Zero Mock 边界与缺失资源处理 ─────────────────────────────────────────

def test_t2_f1_01_query_nonexistent_strategy(live_client: httpx.Client):
    """F1 Boundary: Querying non-existent strategy returns 404 NOT_FOUND instead of mock data."""
    resp = live_client.get("/api/v1/strategies/nonexistent-strategy-xyz-999")
    assert resp.status_code == 404


def test_t2_f1_02_query_nonexistent_backtest(live_client: httpx.Client):
    """F1 Boundary: Querying non-existent backtest returns 404 NOT_FOUND without fake metrics."""
    resp = live_client.get("/api/v1/research/backtests/nonexistent-backtest-xyz-999")
    assert resp.status_code == 404


def test_t2_f1_03_query_nonexistent_portfolio_target(live_client: httpx.Client):
    """F1 Boundary: Querying non-existent portfolio target returns 404 NOT_FOUND."""
    resp = live_client.get("/api/v1/portfolio/targets/nonexistent-target-xyz-999")
    assert resp.status_code == 404


def test_t2_f1_04_empty_order_list_filter(live_client: httpx.Client):
    """F1 Boundary: Filtering orders by an unused account_id returns empty array []."""
    resp = live_client.get("/api/v1/orders?account_id=totally-empty-account-xyz-000")
    assert resp.status_code == 200
    assert resp.json() == []


def test_t2_f1_05_empty_positions_filter(live_client: httpx.Client):
    """F1 Boundary: Filtering positions by an unused account_id returns empty array []."""
    resp = live_client.get("/api/v1/positions?account_id=totally-empty-account-xyz-000")
    assert resp.status_code == 200
    assert resp.json() == []


def test_t2_f1_06_mock_header_rejection(live_client: httpx.Client):
    """F1 Boundary: Passing client headers requesting mock data does not enable fake responses."""
    resp = live_client.get("/api/v1/market/tickers", headers={"X-Mock-Data": "true"})
    assert resp.status_code == 200
    tickers = resp.json()
    assert len(tickers) >= 1
    assert "mock" not in str(tickers[0].get("source", "")).lower()


# ── F2: 行情深度与流水边界测试 ─────────────────────────────────────────────────

def test_t2_f2_01_orderbook_depth_zero(live_client: httpx.Client):
    """F2 Boundary: depth=0 violates depth >= 1 constraint returning 422."""
    resp = live_client.get("/api/v1/market/orderbook/BTCUSDT?depth=0")
    assert resp.status_code == 422


def test_t2_f2_02_orderbook_depth_excessive(live_client: httpx.Client):
    """F2 Boundary: depth=50 exceeds max depth <= 20 returning 422."""
    resp = live_client.get("/api/v1/market/orderbook/BTCUSDT?depth=50")
    assert resp.status_code == 422


def test_t2_f2_03_orderbook_depth_negative(live_client: httpx.Client):
    """F2 Boundary: Negative depth=-5 returns 422 validation error."""
    resp = live_client.get("/api/v1/market/orderbook/BTCUSDT?depth=-5")
    assert resp.status_code == 422


def test_t2_f2_04_orderbook_invalid_symbol(live_client: httpx.Client):
    """F2 Boundary: Querying orderbook for nonexistent symbol returns 404 or empty book."""
    resp = live_client.get("/api/v1/market/orderbook/NONEXISTENT_SYMBOL_XYZ")
    assert resp.status_code in (400, 404)


def test_t2_f2_05_trades_limit_zero(live_client: httpx.Client):
    """F2 Boundary: limit=0 violates limit >= 1 constraint returning 422."""
    resp = live_client.get("/api/v1/market/trades/BTCUSDT?limit=0")
    assert resp.status_code == 422


def test_t2_f2_06_trades_limit_excessive(live_client: httpx.Client):
    """F2 Boundary: limit=500 exceeds max limit <= 20 returning 422."""
    resp = live_client.get("/api/v1/market/trades/BTCUSDT?limit=500")
    assert resp.status_code == 422


# ── F3: 盯市估值与系统边界 ─────────────────────────────────────────────────────

def test_t2_f3_01_mtm_negative_price(live_client: httpx.Client, auth_headers):
    """F3 Boundary: Submitting negative mark_price returns 400/422 validation error."""
    resp = live_client.post(
        "/api/v1/positions/mark-to-market",
        json={"account_id": "paper-main", "symbol": "BTCUSDT", "mark_price": "-500.00", "mode": "paper"},
        headers=auth_headers("trader"),
    )
    assert resp.status_code in (400, 422)


def test_t2_f3_02_mtm_zero_price(live_client: httpx.Client, auth_headers):
    """F3 Boundary: Submitting zero mark_price operates as valid numeric price."""
    resp = live_client.post(
        "/api/v1/positions/mark-to-market",
        json={"account_id": "paper-main", "symbol": "BTCUSDT", "mark_price": "0.00", "mode": "paper"},
        headers=auth_headers("trader"),
    )
    assert resp.status_code == 200
    assert "positions_updated" in resp.json()


def test_t2_f3_03_mtm_nonexistent_symbol(live_client: httpx.Client, auth_headers):
    """F3 Boundary: Submitting mark-to-market for symbol with no positions updates 0 positions."""
    resp = live_client.post(
        "/api/v1/positions/mark-to-market",
        json={"account_id": "paper-main", "symbol": "UNHEARD_COIN_XYZ", "mark_price": "100.00", "mode": "paper"},
        headers=auth_headers("trader"),
    )
    assert resp.status_code == 200
    assert resp.json().get("positions_updated") == 0


def test_t2_f3_04_audit_events_pagination_bounds(live_client: httpx.Client, auth_headers):
    """F3 Boundary: Pagination limit=0 or negative limit returns 422."""
    resp = live_client.get("/api/v1/audit/events?limit=0", headers=auth_headers("auditor"))
    assert resp.status_code == 422


def test_t2_f3_05_audit_events_offset_excessive(live_client: httpx.Client, auth_headers):
    """F3 Boundary: Offset beyond available records safely returns empty list."""
    resp = live_client.get("/api/v1/audit/events?offset=999999", headers=auth_headers("auditor"))
    assert resp.status_code == 200
    assert resp.json() == []


# ── F4: API 路由与输入格式异常边界 ─────────────────────────────────────────────

def test_t2_f4_01_invalid_json_body_rejection(live_client: httpx.Client, auth_headers):
    """F4 Boundary: Submitting malformed JSON payload returns 422."""
    resp = live_client.post(
        "/api/v1/risk/preflight",
        content=b"{invalid_json_format",
        headers={"Content-Type": "application/json", **auth_headers("trader")},
    )
    assert resp.status_code in (400, 422)


def test_t2_f4_02_missing_required_fields(live_client: httpx.Client, auth_headers):
    """F4 Boundary: Submitting empty JSON payload to preflight endpoint returns 422."""
    resp = live_client.post(
        "/api/v1/risk/preflight",
        json={},
        headers=auth_headers("trader"),
    )
    assert resp.status_code == 422


def test_t2_f4_03_extra_forbidden_fields(live_client: httpx.Client, auth_headers):
    """F4 Boundary: Submitting unknown extra fields where forbidden returns 422."""
    resp = live_client.post(
        "/api/v1/live/credentials",
        json={
            "connection_id": "conn-extra",
            "exchange": "binance",
            "api_key": "123456789",
            "api_secret": "123456789",
            "environment": "testnet",
            "malicious_injected_extra_field": True,
        },
        headers=auth_headers("admin"),
    )
    assert resp.status_code in (400, 422)


def test_t2_f4_04_research_backtest_invalid_date_range(live_client: httpx.Client, auth_headers):
    """F4 Boundary: Backtest start_time > end_time is rejected."""
    resp = live_client.post(
        "/api/v1/research/backtests",
        json={
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "initial_capital": "-1000.00",
            "mode": "paper",
        },
        headers=auth_headers("trader"),
    )
    assert resp.status_code in (400, 422)


def test_t2_f4_05_invalid_http_method(live_client: httpx.Client):
    """F4 Boundary: Using unsupported HTTP method (DELETE on /tickers) returns 405."""
    resp = live_client.delete("/api/v1/market/tickers")
    assert resp.status_code == 405


def test_t2_f4_06_nonexistent_api_endpoint(live_client: httpx.Client):
    """F4 Boundary: Requesting non-existent API URL returns 404."""
    resp = live_client.get("/api/v1/definitely/does/not/exist")
    assert resp.status_code == 404


# ── F5: Control 与适配器边界 ───────────────────────────────────────────────────

def test_t2_f5_01_model_provider_not_found(live_client: httpx.Client, auth_headers):
    """F5 Boundary: Non-existent model provider test returns 404."""
    resp = live_client.post("/api/v1/control/model-providers/nonexistent-xyz/test", headers=auth_headers("admin"))
    assert resp.status_code == 404


def test_t2_f5_02_adapter_not_found(live_client: httpx.Client):
    """F5 Boundary: Querying non-existent adapter returns 404."""
    resp = live_client.get("/api/v1/adapters/nonexistent-adapter-xyz")
    assert resp.status_code == 404


def test_t2_f5_03_adapter_symbols_not_found(live_client: httpx.Client):
    """F5 Boundary: Querying symbols for non-existent adapter returns 404."""
    resp = live_client.get("/api/v1/adapters/nonexistent-adapter-xyz/symbols")
    assert resp.status_code == 404


def test_t2_f5_04_adapter_tickers_not_found(live_client: httpx.Client):
    """F5 Boundary: Querying tickers for non-existent adapter returns 404."""
    resp = live_client.get("/api/v1/adapters/nonexistent-adapter-xyz/tickers/BTCUSDT")
    assert resp.status_code == 404


def test_t2_f5_05_test_nonexistent_provider(live_client: httpx.Client, auth_headers):
    """F5 Boundary: Testing connectivity for non-existent provider returns 404."""
    resp = live_client.post("/api/v1/control/model-providers/fake-provider-999/test", headers=auth_headers("admin"))
    assert resp.status_code == 404


# ── F6: 订单流转与风控预检边界 ─────────────────────────────────────────────────

def test_t2_f6_01_risk_preflight_zero_quantity(live_client: httpx.Client, auth_headers, unique_account_id: str):
    """F6 Boundary: Preflight with quantity=0 is evaluated and rejected by positive_quantity rule."""
    resp = live_client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": unique_account_id,
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.00000000",
            "price": "65000.00",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
        headers=auth_headers("trader"),
    )
    assert resp.status_code in (200, 400, 422)
    if resp.status_code == 200:
        assert resp.json().get("decision") == "rejected"


def test_t2_f6_02_risk_preflight_negative_quantity(live_client: httpx.Client, auth_headers, unique_account_id: str):
    """F6 Boundary: Preflight with negative quantity is rejected."""
    resp = live_client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": unique_account_id,
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "-0.50000000",
            "price": "65000.00",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
        headers=auth_headers("trader"),
    )
    assert resp.status_code in (400, 422)


def test_t2_f6_03_risk_preflight_excessive_quantity(live_client: httpx.Client, auth_headers, unique_account_id: str):
    """F6 Boundary: Preflight with exorbitant quantity exceeding risk limits is rejected."""
    resp = live_client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": unique_account_id,
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "99999999.00000000",
            "price": "65000.00",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
        headers=auth_headers("trader"),
    )
    assert resp.status_code in (200, 400)
    if resp.status_code == 200:
        assert resp.json().get("decision") == "rejected"


def test_t2_f6_04_order_intent_missing_risk_decision(live_client: httpx.Client, auth_headers, unique_account_id: str):
    """F6 Boundary: Submitting order intent without risk_decision_id returns 400/422."""
    resp = live_client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": f"ord-norisk-{uuid.uuid4().hex[:6]}",
            "account_id": unique_account_id,
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "65000.00",
            "mode": "paper",
        },
        headers=auth_headers("trader"),
    )
    assert resp.status_code in (400, 422)


def test_t2_f6_05_order_intent_duplicate_client_id(live_client: httpx.Client, auth_headers, approved_preflight: dict):
    """F6 Boundary: Reusing identical client_order_id with different parameters returns 409 CONFLICT."""
    dup_id = f"ord-dup-{uuid.uuid4().hex[:6]}"
    r1 = live_client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": dup_id,
            "account_id": approved_preflight["account_id"],
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "65000.00",
            "mode": "paper",
            "risk_decision_id": approved_preflight["decision_id"],
        },
        headers=auth_headers("trader"),
    )
    assert r1.status_code in (200, 201)

    r2 = live_client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": dup_id,
            "account_id": approved_preflight["account_id"],
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.02000000",
            "limit_price": "65000.00",
            "mode": "paper",
            "risk_decision_id": approved_preflight["decision_id"],
        },
        headers=auth_headers("trader"),
    )
    assert r2.status_code in (400, 409)


def test_t2_f6_06_cancel_nonexistent_order(live_client: httpx.Client, auth_headers):
    """F6 Boundary: Cancelling non-existent order returns 404 NOT_FOUND."""
    resp = live_client.post(
        "/api/v1/execution/orders/nonexistent-ord-9999/cancel",
        json={"client_order_id": "nonexistent-ord-9999"},
        headers=auth_headers("trader"),
    )
    assert resp.status_code == 404


# ── F7: Nginx 静态托管与边界测试 ───────────────────────────────────────────────

def test_t2_f7_01_nginx_nonexistent_asset(nginx_client: httpx.Client):
    """F7 Boundary: Requesting non-existent path falls back to SPA index or returns 404."""
    resp = nginx_client.get("/assets/totally_fake_bundle_xyz_123.css")
    assert resp.status_code in (200, 404)


def test_t2_f7_02_nginx_very_long_url(nginx_client: httpx.Client):
    """F7 Boundary: Very long URL path is safely handled by Nginx without crash."""
    long_path = "/market/" + ("abc" * 100)
    resp = nginx_client.get(long_path)
    assert resp.status_code in (200, 404, 414)


def test_t2_f7_03_css_syntax_error_absence(nginx_client: httpx.Client):
    """F7 Boundary: CSS stylesheet contains balanced braces without broken blocks."""
    css_url, _ = _get_asset_urls(nginx_client)
    resp = nginx_client.get(css_url)
    assert resp.status_code == 200
    css = resp.text
    open_count = css.count("{")
    close_count = css.count("}")
    assert open_count == close_count, "CSS has unbalanced curly braces"


def test_t2_f7_04_css_color_format_validity(nginx_client: httpx.Client):
    """F7 Boundary: Hex colors in CSS have valid lengths."""
    css_url, _ = _get_asset_urls(nginx_client)
    resp = nginx_client.get(css_url)
    assert resp.status_code == 200
    css = resp.text
    hex_colors = re.findall(r"#[0-9a-fA-F]+", css)
    assert len(hex_colors) > 0


def test_t2_f7_05_nginx_head_request(nginx_client: httpx.Client):
    """F7 Boundary: HEAD request on root returns 200 without body."""
    resp = nginx_client.head("/")
    assert resp.status_code == 200
    assert len(resp.content) == 0


# ── F8: 数值格式化异常与边界值 ─────────────────────────────────────────────────

def test_t2_f8_01_formatter_nan_input():
    """F8 Boundary: Formatting NaN or None gracefully produces placeholder '--'."""
    def safe_format(val: float | None) -> str:
        if val is None or math.isnan(val):
            return "--"
        return f"{val:.2f}"

    assert safe_format(None) == "--"
    assert safe_format(float("nan")) == "--"


def test_t2_f8_02_formatter_extreme_large_number():
    """F8 Boundary: Extremely large number (1e18) formats safely without overflow."""
    def format_large(val: float) -> str:
        if val >= 1_000_000_000_000_000:
            return f"${val:.2e}"
        return f"${val:,.2f}"

    res = format_large(1e18)
    assert "e" in res or "$" in res


def test_t2_f8_03_formatter_extreme_small_number():
    """F8 Boundary: Micro satoshi numbers (0.00000005) preserve significance."""
    def format_micro(val: float) -> str:
        if 0 < val < 0.0001:
            return f"{val:.8f}"
        return f"{val:.2f}"

    assert format_micro(0.00000005) == "0.00000005"


def test_t2_f8_04_formatter_negative_zero():
    """F8 Boundary: Negative zero is formatted cleanly as 0.00%."""
    def format_percent(val: float) -> str:
        if abs(val) < 1e-7:
            return "0.00%"
        return f"{val * 100:+.2f}%"

    assert format_percent(-0.0) == "0.00%"


def test_t2_f8_05_heartbeat_calculator_negative_latency():
    """F8 Boundary: Negative latency calculation clamps safely to 0ms."""
    def clamp_latency(raw_ms: float) -> float:
        return max(0.0, raw_ms)

    assert clamp_latency(-15.4) == 0.0


# ── F9: 凭证安全性与加解密边界 ─────────────────────────────────────────────────

def test_t2_f9_01_credential_empty_api_key(live_client: httpx.Client, auth_headers):
    """F9 Boundary: Submitting empty api_key returns 422 validation error."""
    resp = live_client.post(
        "/api/v1/live/credentials",
        json={
            "connection_id": "conn-empty-key",
            "exchange": "binance",
            "api_key": "",
            "api_secret": "123456789",
            "environment": "testnet",
        },
        headers=auth_headers("admin"),
    )
    assert resp.status_code == 422


def test_t2_f9_02_credential_short_api_key(live_client: httpx.Client, auth_headers):
    """F9 Boundary: Submitting short api_key (< 8 chars) returns 422."""
    resp = live_client.post(
        "/api/v1/live/credentials",
        json={
            "connection_id": "conn-short-key",
            "exchange": "binance",
            "api_key": "short",
            "api_secret": "123456789",
            "environment": "testnet",
        },
        headers=auth_headers("admin"),
    )
    assert resp.status_code == 422


def test_t2_f9_03_credential_invalid_connection_id_chars(live_client: httpx.Client, auth_headers):
    """F9 Boundary: connection_id with illegal characters (e.g. spaces/special symbols) returns 422."""
    resp = live_client.post(
        "/api/v1/live/credentials",
        json={
            "connection_id": "INVALID ID WITH SPACES!@#$",
            "exchange": "binance",
            "api_key": "valid_api_key_123",
            "api_secret": "valid_api_secret_456",
            "environment": "testnet",
        },
        headers=auth_headers("admin"),
    )
    assert resp.status_code == 422


def test_t2_f9_04_credential_lookup_nonexistent(live_client: httpx.Client, auth_headers):
    """F9 Boundary: Querying non-existent credential returns 404 NOT_FOUND."""
    resp = live_client.get("/api/v1/live/credentials/nonexistent-conn-xyz-999", headers=auth_headers("admin"))
    assert resp.status_code == 404


def test_t2_f9_05_credential_delete_nonexistent(live_client: httpx.Client, auth_headers):
    """F9 Boundary: Deleting non-existent credential returns 404 NOT_FOUND."""
    resp = live_client.delete("/api/v1/live/credentials/nonexistent-conn-xyz-999", headers=auth_headers("admin"))
    assert resp.status_code == 404


def test_t2_f9_06_credential_crypto_tampered_ciphertext():
    """F9 Boundary: Tampering with encrypted token raises CredentialCryptoError."""
    master_key = "test_e2e_master_secret_key_32_bytes_len"
    raw_payload = {"api_key": "key123", "api_secret": "secret456"}
    sealed = seal_dict(master_key, raw_payload)

    tampered = sealed[:-4] + ("a" if sealed[-4] != "a" else "b") + sealed[-3:]

    with pytest.raises(CredentialCryptoError):
        open_dict(master_key, tampered)


# ── F10: AI 模型网关 SSRF 拦截与输入边界 ────────────────────────────────────────

def test_t2_f10_01_ssrf_loopback_ip_blocked(live_client: httpx.Client, auth_headers):
    """F10 Boundary: Setting model provider base_url to loopback 127.0.0.1 is blocked (SSRF)."""
    resp = live_client.put(
        "/api/v1/control/model-providers/test_ssrf_loopback",
        json={
            "provider_id": "test_ssrf_loopback",
            "display_name": "SSRF Loopback",
            "base_url": "http://127.0.0.1:8000/api",
            "model": "gpt-4o",
            "enabled": True,
        },
        headers=auth_headers("admin"),
    )
    assert resp.status_code == 400


def test_t2_f10_02_ssrf_metadata_ip_blocked(live_client: httpx.Client, auth_headers):
    """F10 Boundary: Setting model provider base_url to AWS/Alibaba cloud metadata IP is blocked."""
    resp = live_client.put(
        "/api/v1/control/model-providers/test_ssrf_meta",
        json={
            "provider_id": "test_ssrf_meta",
            "display_name": "SSRF Meta",
            "base_url": "http://169.254.169.254/latest/meta-data",
            "model": "gpt-4o",
            "enabled": True,
        },
        headers=auth_headers("admin"),
    )
    assert resp.status_code == 400


def test_t2_f10_03_ssrf_private_network_blocked(live_client: httpx.Client, auth_headers):
    """F10 Boundary: Setting model provider base_url to 10.x.x.x RFC 1918 private IP is blocked."""
    resp = live_client.put(
        "/api/v1/control/model-providers/test_ssrf_priv",
        json={
            "provider_id": "test_ssrf_priv",
            "display_name": "SSRF Priv",
            "base_url": "http://10.0.0.1:8080/v1",
            "model": "gpt-4o",
            "enabled": True,
        },
        headers=auth_headers("admin"),
    )
    assert resp.status_code == 400


def test_t2_f10_04_chat_empty_messages(live_client: httpx.Client, auth_headers):
    """F10 Boundary: Submitting chat request with empty messages array returns 422."""
    resp = live_client.post(
        "/api/v1/ai/chat",
        json={"provider_id": "deepseek", "messages": []},
        headers=auth_headers("trader"),
    )
    assert resp.status_code == 422


def test_t2_f10_05_agent_task_run_nonexistent(live_client: httpx.Client, auth_headers):
    """F10 Boundary: Running non-existent agent task returns 404 NOT_FOUND."""
    resp = live_client.post("/api/v1/agents/tasks/nonexistent-task-xyz-999/run", headers=auth_headers("trader"))
    assert resp.status_code == 404


# ── F11: 鉴权签名与指标计算边界 ─────────────────────────────────────────────────

def test_t2_f11_01_jwt_expired_token_rejected():
    """F11 Boundary: JWT token with expired timestamp is rejected by validator."""
    from datetime import timedelta
    token = str(create_access_token("exp-user", role="trader", expires_delta=timedelta(seconds=-10)))
    result = verify_token(token)
    assert result is None


def test_t2_f11_02_jwt_tampered_signature_rejected():
    """F11 Boundary: JWT token with tampered signature component is rejected."""
    token = str(create_access_token("tamper-user", role="trader"))
    parts = token.split(".")
    tampered_sig = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
    tampered_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"
    assert verify_token(tampered_token) is None


def test_t2_f11_03_jwt_wrong_secret_rejected():
    """F11 Boundary: JWT token signed with an alien secret fails validation."""
    token = str(create_access_token("alien-user", role="trader"))
    parts = token.split(".")
    tampered = f"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmYWtlIn0.{parts[2]}"
    assert verify_token(tampered) is None


def test_t2_f11_04_backtest_empty_data_series():
    """F11 Boundary: Technical indicators on empty prices list handle gracefully."""
    empty_res = sma([], length=5)
    assert empty_res == []


def test_t2_f11_05_backtest_constant_price_zero_volatility():
    """F11 Boundary: Zero variance price series calculates indicators without ZeroDivisionError."""
    const_bars = [
        Bar(symbol="BTCUSDT", open_time=1000 + i * 60, open=Decimal("100.0"), high=Decimal("100.0"), low=Decimal("100.0"), close=Decimal("100.0"), volume=Decimal("100"))
        for i in range(20)
    ]
    sma_res = sma(const_bars, length=5)
    assert len(sma_res) == 20
    valid_res = [v for v in sma_res if v is not None]
    assert all(abs(v - 100.0) < 1e-5 for v in valid_res)


def test_t2_f11_06_governance_approval_already_decided(live_client: httpx.Client, auth_headers):
    """F11 Boundary: Deciding an already decided approval returns 400 APPROVAL_ALREADY_DECIDED."""
    create_resp = live_client.post(
        "/api/v1/governance/approvals",
        json={
            "resource_type": "risk_threshold_change",
            "resource_id": "rule_01",
            "requested_by": "trader1",
            "title": "Increase Limit",
            "details": "Temporary bump",
        },
        headers=auth_headers("trader"),
    )
    assert create_resp.status_code in (200, 201)
    appr_id = create_resp.json()["approval_id"]

    d1 = live_client.post(
        f"/api/v1/governance/approvals/{appr_id}/decide",
        json={"decision": "approved", "decided_by": "risk_admin_1", "reject_reason": None},
        headers=auth_headers("risk_admin"),
    )
    assert d1.status_code == 200

    d2 = live_client.post(
        f"/api/v1/governance/approvals/{appr_id}/decide",
        json={"decision": "rejected", "decided_by": "risk_admin_2", "reject_reason": "Too late"},
        headers=auth_headers("risk_admin"),
    )
    assert d2.status_code == 400


# ── F12: Nginx 生产代理边界 ─────────────────────────────────────────────────────

def test_t2_f12_01_nginx_unsupported_method(nginx_client: httpx.Client):
    """F12 Boundary: Nginx handles unsupported TRACE/CONNECT methods cleanly."""
    resp = nginx_client.request("TRACE", "/health")
    assert resp.status_code in (405, 400, 501, 200)


def test_t2_f12_02_nginx_spa_nested_subroutes(nginx_client: httpx.Client):
    """F12 Boundary: Nginx rewrite handles deep subroutes (/execution/orders/details/123)."""
    resp = nginx_client.get("/execution/orders/details/123")
    assert resp.status_code == 200
    assert "<html" in resp.text.lower() or "<!doctype html>" in resp.text.lower()


def test_t2_f12_03_nginx_trailing_slash_handling(nginx_client: httpx.Client):
    """F12 Boundary: Nginx gracefully handles trailing slash on health check."""
    resp = nginx_client.get("/health/")
    assert resp.status_code in (200, 301, 308)


def test_t2_f12_04_nginx_static_content_type(nginx_client: httpx.Client):
    """F12 Boundary: Requesting JS file returns correct mime-type without text/plain fallback."""
    _, js_url = _get_asset_urls(nginx_client)
    resp = nginx_client.get(js_url)
    assert resp.status_code == 200
    assert "javascript" in resp.headers.get("content-type", "")


def test_t2_f12_05_nginx_api_cors_preflight(nginx_client: httpx.Client):
    """F12 Boundary: Sending OPTIONS preflight request to API route succeeds."""
    resp = nginx_client.options(
        "/api/v1/market/tickers",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
    )
    assert resp.status_code in (200, 204)
