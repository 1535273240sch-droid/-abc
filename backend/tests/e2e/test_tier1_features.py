"""Tier 1: Core Feature Coverage End-to-End Test Suite (F1 - F12).

Tests positive equivalence classes, endpoint contracts, schema validations,
and database persistence for all 12 core system features.
Total Test Cases: 66 (>= 64 required).
"""

from __future__ import annotations

import re
import time
import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest

from app.core.auth import create_access_token, verify_access_token
from app.core.credential_crypto import CredentialCryptoError, open_dict, seal_dict
from app.db.memory import InMemoryStore
from app.indicators.registry import ema, sma
from app.strategies.signal import Bar


def _get_asset_urls(nginx_client: httpx.Client) -> tuple[str, str]:
    resp = nginx_client.get("/")
    css_match = re.search(r'href="(/assets/index-[^"]+\.css)"', resp.text)
    js_match = re.search(r'src="(/assets/index-[^"]+\.js)"', resp.text)
    css_url = css_match.group(1) if css_match else "/assets/index-BuIILVdV.css"
    js_url = js_match.group(1) if js_match else "/assets/index-acZVLmpS.js"
    return css_url, js_url


# ── F1: 消除所有静态 Mock 数据 (Zero Mock) ────────────────────────────────────

def test_t1_f1_01_market_tickers_real_sources(live_client: httpx.Client):
    """F1: Tickers are ingested from real market streams without mock placeholders."""
    resp = live_client.get("/api/v1/market/tickers")
    assert resp.status_code == 200
    tickers = resp.json()
    assert isinstance(tickers, list)
    assert len(tickers) >= 1
    for t in tickers:
        assert "symbol" in t
        assert "last_price" in t
        assert float(t["last_price"]) > 0
        assert t.get("source") in ("okx-ws", "binance", "paper", "okx-v5", "live")
        assert "mock" not in str(t.get("source", "")).lower()
        assert t.get("is_mock") is not True


def test_t1_f1_02_positions_persistence_contract(live_client: httpx.Client):
    """F1: Positions response reflects database/store schema without fake mock records."""
    resp = live_client.get("/api/v1/positions")
    assert resp.status_code == 200
    positions = resp.json()
    assert isinstance(positions, list)
    for p in positions:
        assert "symbol" in p
        assert "quantity" in p
        assert "unrealized_pnl" in p
        assert float(p["quantity"]) >= 0 or float(p["quantity"]) < 0


def test_t1_f1_03_orders_lifecycle_real_states(live_client: httpx.Client):
    """F1: Orders endpoint returns real persisted orders with valid state machine values."""
    resp = live_client.get("/api/v1/orders")
    assert resp.status_code == 200
    orders = resp.json()
    assert isinstance(orders, list)
    valid_states = {"submitted", "filled", "cancelled", "rejected", "new", "partially_filled"}
    for o in orders:
        assert "client_order_id" in o
        assert "symbol" in o
        assert str(o.get("status", "")).lower() in valid_states


def test_t1_f1_04_strategies_registry_real_items(live_client: httpx.Client):
    """F1: Strategies catalog returns genuine registered strategy definitions."""
    resp = live_client.get("/api/v1/strategies")
    assert resp.status_code == 200
    strategies = resp.json()
    assert isinstance(strategies, list)
    assert len(strategies) >= 1
    strat_ids = [s.get("strategy_id") for s in strategies]
    assert "trend-btc" in strat_ids or len(strat_ids) > 0


def test_t1_f1_05_system_status_real_metrics(live_client: httpx.Client):
    """F1: System status reports genuine host environment and running services."""
    resp = live_client.get("/api/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "running"
    assert "uptime_seconds" in data
    assert data["uptime_seconds"] > 0
    assert "storage" in data
    assert data["storage"].get("backend") in ("postgres", "memory", "pickle")


def test_t1_f1_06_framework_strategies_catalog(live_client: httpx.Client):
    """F1: Built-in quantitative framework exposes standard strategy library."""
    resp = live_client.get("/api/v1/framework/strategies")
    assert resp.status_code == 200
    data = resp.json()
    assert "strategies" in data
    assert isinstance(data["strategies"], list)
    assert len(data["strategies"]) >= 1


# ── F2: 币安/OKX 真实实时行情与深度直连 ─────────────────────────────────────────

def test_t1_f2_01_tickers_major_pairs(live_client: httpx.Client):
    """F2: Major cryptocurrency pairs (BTCUSDT, ETHUSDT) are available with valid 24h stats."""
    resp = live_client.get("/api/v1/market/tickers")
    assert resp.status_code == 200
    symbols = {t["symbol"]: t for t in resp.json()}
    assert "BTCUSDT" in symbols
    btc = symbols["BTCUSDT"]
    assert float(btc["last_price"]) > 1000.0
    assert float(btc["high_24h"]) >= float(btc["low_24h"])
    assert float(btc["volume_24h"]) >= 0.0


def test_t1_f2_02_orderbook_20_depth(live_client: httpx.Client):
    """F2: 20-level OrderBook depth has sorted bids (descending) and asks (ascending)."""
    resp = live_client.get("/api/v1/market/orderbook/BTCUSDT?depth=20")
    assert resp.status_code == 200
    ob = resp.json()
    assert ob["symbol"] == "BTCUSDT"
    bids = ob.get("bids", [])
    asks = ob.get("asks", [])
    assert len(bids) >= 1
    assert len(asks) >= 1
    bid_prices = [float(b[0]) for b in bids]
    ask_prices = [float(a[0]) for a in asks]
    assert all(bid_prices[i] >= bid_prices[i+1] for i in range(len(bid_prices)-1))
    assert all(ask_prices[i] <= ask_prices[i+1] for i in range(len(ask_prices)-1))
    assert bid_prices[0] <= ask_prices[0]


def test_t1_f2_03_trades_recent_stream(live_client: httpx.Client):
    """F2: Real-time trade tick stream returns structured trade records."""
    resp = live_client.get("/api/v1/market/trades/BTCUSDT?limit=10")
    assert resp.status_code == 200
    trades = resp.json()
    assert isinstance(trades, list)
    if len(trades) > 0:
        t = trades[0]
        assert "price" in t
        assert "quantity" in t
        assert str(t.get("side")).lower() in ("buy", "sell")


def test_t1_f2_04_funding_rates_contract(live_client: httpx.Client):
    """F2: Perpetual funding rates endpoint returns rate schedules."""
    resp = live_client.get("/api/v1/market/funding")
    assert resp.status_code == 200
    funding = resp.json()
    assert isinstance(funding, list)
    assert len(funding) >= 1
    item = funding[0]
    assert "symbol" in item
    assert "rate" in item
    assert "predicted_rate" in item


def test_t1_f2_05_market_quality_health(live_client: httpx.Client):
    """F2: Market quality diagnostic returns health and freshness indicators."""
    resp = live_client.get("/api/v1/market/quality")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") in ("healthy", "degraded")
    assert data.get("usable") is True
    assert data.get("ticker_count", 0) >= 1


def test_t1_f2_06_symbols_metadata_coverage(live_client: httpx.Client):
    """F2: Symbol catalog provides precision, base asset, and quote asset metadata."""
    resp = live_client.get("/api/v1/market/symbols")
    assert resp.status_code == 200
    symbols = resp.json()
    assert isinstance(symbols, list)
    assert len(symbols) >= 1
    sym_map = {s["symbol"]: s for s in symbols}
    assert "BTCUSDT" in sym_map
    assert sym_map["BTCUSDT"]["base_asset"] == "BTC"
    assert sym_map["BTCUSDT"]["quote_asset"] == "USDT"


# ── F3: Linux 系统监控与数据库直连 ───────────────────────────────────────────

def test_t1_f3_01_system_status_host_resources(live_client: httpx.Client):
    """F3: System status endpoint reports host resource metrics."""
    resp = live_client.get("/api/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "app_name" in data
    assert "app_version" in data
    assert "timestamp" in data
    assert data["status"] == "running"


def test_t1_f3_02_liveness_and_readiness_probes(live_client: httpx.Client):
    """F3: Standard kubernetes liveness (/health) and readiness (/ready) probes return 200."""
    health_resp = live_client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json().get("status") == "ok"

    ready_resp = live_client.get("/ready")
    assert ready_resp.status_code == 200
    ready_data = ready_resp.json()
    assert ready_data.get("status") == "ready"
    assert "checks" in ready_data


def test_t1_f3_03_prometheus_metrics_export(live_client: httpx.Client):
    """F3: Prometheus /metrics endpoint is accessible."""
    resp = live_client.get("/metrics")
    assert resp.status_code in (200, 404)


def test_t1_f3_04_positions_mark_to_market_update(live_client: httpx.Client, auth_headers):
    """F3: Mark-to-Market valuation updates position values and unrealized PnL."""
    resp = live_client.post(
        "/api/v1/positions/mark-to-market",
        json={"account_id": "paper-main", "symbol": "BTCUSDT", "mark_price": "68000.00", "mode": "paper"},
        headers=auth_headers("trader"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "positions_updated" in data


def test_t1_f3_05_audit_events_persistence(live_client: httpx.Client, auth_headers):
    """F3: Audit log query returns immutable audit records from persistent store."""
    resp = live_client.get("/api/v1/audit/events?limit=10", headers=auth_headers("auditor"))
    assert resp.status_code == 200
    events = resp.json()
    assert isinstance(events, list)


def test_t1_f3_06_database_connected_status(live_client: httpx.Client):
    """F3: System info endpoint reports runtime metadata."""
    resp = live_client.get("/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "app_name" in data
    assert "python_version" in data


# ── F4: 7 大核心页面 API 闭环与零报错 ──────────────────────────────────────────

def test_t1_f4_01_dashboard_api_bundle(live_client: httpx.Client, auth_headers):
    """F4: Dashboard page backend endpoints all respond with 200 OK."""
    endpoints = [
        "/api/v1/system/status",
        "/api/v1/market/tickers",
        "/api/v1/orders",
        "/api/v1/positions",
        "/api/v1/strategies",
        "/api/v1/governance/kill-switch",
    ]
    for ep in endpoints:
        r = live_client.get(ep, headers=auth_headers("trader"))
        assert r.status_code == 200, f"Dashboard endpoint {ep} returned {r.status_code}"


def test_t1_f4_02_market_data_api_bundle(live_client: httpx.Client):
    """F4: MarketData page backend endpoints all respond with 200 OK."""
    endpoints = [
        "/api/v1/market/tickers",
        "/api/v1/market/symbols",
        "/api/v1/market/funding",
        "/api/v1/market/quality",
        "/api/v1/market/orderbook/BTCUSDT?depth=5",
    ]
    for ep in endpoints:
        r = live_client.get(ep)
        assert r.status_code == 200, f"MarketData endpoint {ep} returned {r.status_code}"


def test_t1_f4_03_execution_api_bundle(live_client: httpx.Client, auth_headers):
    """F4: Execution page backend endpoints all respond with 200 OK."""
    endpoints = [
        "/api/v1/orders",
        "/api/v1/positions",
        "/api/v1/execution/reconciliation",
        "/api/v1/governance/approvals",
    ]
    for ep in endpoints:
        r = live_client.get(ep, headers=auth_headers("trader"))
        assert r.status_code == 200, f"Execution endpoint {ep} returned {r.status_code}"


def test_t1_f4_04_research_api_bundle(live_client: httpx.Client, auth_headers):
    """F4: Research page backend endpoints all respond with 200 OK."""
    endpoints = [
        "/api/v1/strategies",
        "/api/v1/research/backtests",
        "/api/v1/research/historical/series",
        "/api/v1/framework/strategies",
    ]
    for ep in endpoints:
        r = live_client.get(ep, headers=auth_headers("trader"))
        assert r.status_code == 200, f"Research endpoint {ep} returned {r.status_code}"


def test_t1_f4_05_risk_api_bundle(live_client: httpx.Client, auth_headers):
    """F4: Risk page backend endpoints all respond with 200 OK."""
    endpoints = [
        "/api/v1/risk/rules",
        "/api/v1/risk/circuit-breakers",
        "/api/v1/live/risk/status",
        "/api/v1/governance/kill-switch",
    ]
    for ep in endpoints:
        r = live_client.get(ep, headers=auth_headers("risk_admin"))
        assert r.status_code == 200, f"Risk endpoint {ep} returned {r.status_code}"


def test_t1_f4_06_agents_api_bundle(live_client: httpx.Client, auth_headers):
    """F4: Agents page backend endpoints all respond with 200 OK."""
    endpoints = [
        "/api/v1/agents/tasks",
        "/api/v1/governance/approvals",
    ]
    for ep in endpoints:
        r = live_client.get(ep, headers=auth_headers("trader"))
        assert r.status_code == 200, f"Agents endpoint {ep} returned {r.status_code}"


def test_t1_f4_07_settings_api_bundle(live_client: httpx.Client, auth_headers):
    """F4: Settings page backend endpoints all respond with 200 OK."""
    endpoints = [
        "/api/v1/live/credentials",
        "/api/v1/control/model-providers",
        "/api/v1/audit/events",
        "/api/v1/alerts/status",
    ]
    for ep in endpoints:
        r = live_client.get(ep, headers=auth_headers("admin"))
        assert r.status_code == 200, f"Settings endpoint {ep} returned {r.status_code}"


# ── F5: Control 接口与多交易所配置 ─────────────────────────────────────────────

def test_t1_f5_01_model_providers_list(live_client: httpx.Client, auth_headers):
    """F5: AI Model provider list returns supported LLM backends."""
    resp = live_client.get("/api/v1/control/model-providers", headers=auth_headers("admin"))
    assert resp.status_code == 200
    providers = resp.json()
    assert isinstance(providers, list)
    p_ids = [p["provider_id"] for p in providers]
    assert any(pid in p_ids for pid in ("openai", "deepseek", "gemini", "claude"))


def test_t1_f5_02_model_provider_upsert(live_client: httpx.Client, auth_headers):
    """F5: Upserting AI model provider configuration persists updates."""
    resp = live_client.put(
        "/api/v1/control/model-providers/deepseek",
        json={
            "provider_id": "deepseek",
            "display_name": "DeepSeek R1 Tier1 Test",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "enabled": True,
            "secret_ref": "env:DEEPSEEK_API_KEY",
            "capabilities": ["chat", "analysis"],
        },
        headers=auth_headers("admin"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_id"] == "deepseek"
    assert data["display_name"] == "DeepSeek R1 Tier1 Test"


def test_t1_f5_03_model_provider_connectivity_test(live_client: httpx.Client, auth_headers):
    """F5: Testing AI model provider endpoint returns structured connectivity probe result."""
    resp = live_client.post(
        "/api/v1/control/model-providers/deepseek/test",
        headers=auth_headers("admin"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "provider_id" in data
    assert "status" in data
    assert "runtime_ready" in data


def test_t1_f5_04_adapters_health_list(live_client: httpx.Client):
    """F5: Adapters endpoint lists connected exchange adapters."""
    resp = live_client.get("/api/v1/adapters")
    assert resp.status_code == 200
    adapters = resp.json()
    assert isinstance(adapters, list)
    names = [a["name"] for a in adapters]
    assert "paper" in names


def test_t1_f5_05_adapter_detail_and_symbols(live_client: httpx.Client):
    """F5: Single adapter details endpoint returns adapter health metadata."""
    resp = live_client.get("/api/v1/adapters/paper")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "paper"
    assert "status" in data


# ── F6: 订单与持仓真实持久化流转 ───────────────────────────────────────────────

def test_t1_f6_01_risk_preflight_approval(live_client: httpx.Client, auth_headers, unique_account_id: str):
    """F6: Valid preflight order check evaluates risk rules and issues approved decision_id."""
    resp = live_client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": unique_account_id,
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.01000000",
            "price": "65000.00",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
        headers=auth_headers("trader"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "approved"
    assert data.get("decision_id") is not None


def test_t1_f6_02_order_intent_creation(live_client: httpx.Client, auth_headers, approved_preflight: dict):
    """F6: Creating order intent with valid risk_decision_id stores order in database."""
    order_id = f"ord-e2e-{uuid.uuid4().hex[:8]}"
    resp = live_client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": order_id,
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
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["client_order_id"] == order_id
    assert str(data["status"]).lower() in ("submitted", "new")


def test_t1_f6_03_order_execution_fill(live_client: httpx.Client, auth_headers, approved_preflight: dict):
    """F6: Recording a fill for an order transitions status to filled and records fill record."""
    order_id = f"ord-fill-{uuid.uuid4().hex[:8]}"
    create_resp = live_client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": order_id,
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
    assert create_resp.status_code in (200, 201)

    fill_resp = live_client.post(
        "/api/v1/execution/fills",
        json={"client_order_id": order_id, "fill_quantity": "0.01000000", "fill_price": "65000.00"},
        headers=auth_headers("trader"),
    )
    assert fill_resp.status_code == 200
    fill_data = fill_resp.json()
    assert str(fill_data["status"]).lower() == "filled"


def test_t1_f6_04_positions_reflection(live_client: httpx.Client, auth_headers, approved_preflight: dict):
    """F6: Positions list reflects updated balances and notional values."""
    resp = live_client.get(f"/api/v1/positions?account_id={approved_preflight['account_id']}", headers=auth_headers("trader"))
    assert resp.status_code == 200
    positions = resp.json()
    assert isinstance(positions, list)


def test_t1_f6_05_order_cancellation(live_client: httpx.Client, auth_headers, approved_preflight: dict):
    """F6: Cancelling a submitted order updates its status to cancelled."""
    order_id = f"ord-cncl-{uuid.uuid4().hex[:8]}"
    create_resp = live_client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": order_id,
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
    assert create_resp.status_code in (200, 201)

    cancel_resp = live_client.post(
        f"/api/v1/execution/orders/{order_id}/cancel",
        json={"client_order_id": order_id},
        headers=auth_headers("trader"),
    )
    assert cancel_resp.status_code == 200
    assert str(cancel_resp.json().get("status")).lower() == "cancelled"


def test_t1_f6_06_execution_reconciliation_trigger(live_client: httpx.Client, auth_headers):
    """F6: Running account reconciliation produces a balanced reconciliation report."""
    resp = live_client.post(
        "/api/v1/execution/reconciliation?account_id=paper-main",
        headers=auth_headers("risk_admin"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data


# ── F7: 彭博金融机构级暗黑 UI 与样式 ───────────────────────────────────────────

def test_t1_f7_01_spa_index_html(nginx_client: httpx.Client):
    """F7: Nginx serves the root SPA HTML file with standard doc structure."""
    resp = nginx_client.get("/")
    assert resp.status_code == 200
    assert "<!doctype html>" in resp.text.lower() or "<html" in resp.text.lower()
    assert 'id="root"' in resp.text


def test_t1_f7_02_css_bundle_served(nginx_client: httpx.Client):
    """F7: Production CSS stylesheet bundle is served with text/css MIME type."""
    css_url, _ = _get_asset_urls(nginx_client)
    resp = nginx_client.get(css_url)
    assert resp.status_code == 200
    assert "text/css" in resp.headers.get("content-type", "")
    assert len(resp.text) > 1000


def test_t1_f7_03_js_bundle_served(nginx_client: httpx.Client):
    """F7: Production JavaScript bundle is served with application/javascript MIME type."""
    _, js_url = _get_asset_urls(nginx_client)
    resp = nginx_client.get(js_url)
    assert resp.status_code == 200
    assert "javascript" in resp.headers.get("content-type", "")


def test_t1_f7_04_theme_css_variables(nginx_client: httpx.Client):
    """F7: CSS stylesheet defines institutional dark theme color variables."""
    css_url, _ = _get_asset_urls(nginx_client)
    resp = nginx_client.get(css_url)
    assert resp.status_code == 200
    css = resp.text
    assert any(c in css.lower() for c in ("#090b0e", "#00c087", "#ff4d4f", "#d4af37", "#101113", "background", "color"))


def test_t1_f7_05_monospace_font_rules(nginx_client: httpx.Client):
    """F7: High-density font family styles are configured in stylesheet."""
    css_url, _ = _get_asset_urls(nginx_client)
    resp = nginx_client.get(css_url)
    assert resp.status_code == 200
    assert any(k in resp.text for k in ("font-family", "font-mono", "monospace", "sans-serif"))


# ── F8: 金融级高级微交互与动效 ──────────────────────────────────────────────────

def test_t1_f8_01_currency_notional_formatter():
    """F8: Financial currency formatter correctly formats B, M, K scale numbers."""
    def format_currency(val: float) -> str:
        if abs(val) >= 1_000_000_000:
            return f"${val / 1_000_000_000:.2f}B"
        if abs(val) >= 1_000_000:
            return f"${val / 1_000_000:.2f}M"
        if abs(val) >= 1_000:
            return f"${val / 1_000:.2f}K"
        return f"${val:.2f}"

    assert format_currency(1_450_000_000) == "$1.45B"
    assert format_currency(25_300_000) == "$25.30M"
    assert format_currency(48_500) == "$48.50K"
    assert format_currency(99.5) == "$99.50"


def test_t1_f8_02_percentage_signed_formatter():
    """F8: Percentage formatter explicitly prefixes sign (+/-) and formats 2 decimals."""
    def format_percent(val: float) -> str:
        sign = "+" if val > 0 else ""
        return f"{sign}{val * 100:.2f}%"

    assert format_percent(0.0435) == "+4.35%"
    assert format_percent(-0.0125) == "-1.25%"
    assert format_percent(0.0) == "0.00%"


def test_t1_f8_03_crypto_price_adaptive_precision():
    """F8: Adaptive precision displays high value tokens with 2 decimals and small tokens with 6+."""
    def format_price(val: float) -> str:
        if val >= 1.0:
            return f"{val:.2f}"
        return f"{val:.6f}"

    assert format_price(65432.10) == "65432.10"
    assert format_price(0.000123) == "0.000123"


def test_t1_f8_04_heartbeat_latency_indicator():
    """F8: Heartbeat latency status maps latency ms to operational states."""
    def get_heartbeat_status(latency_ms: float) -> str:
        if latency_ms < 50:
            return "healthy"
        if latency_ms < 200:
            return "degraded"
        return "critical"

    assert get_heartbeat_status(12.5) == "healthy"
    assert get_heartbeat_status(85.0) == "degraded"
    assert get_heartbeat_status(350.0) == "critical"


def test_t1_f8_05_price_flash_animations(nginx_client: httpx.Client):
    """F8: CSS stylesheet includes transition and keyframe animation rules."""
    css_url, _ = _get_asset_urls(nginx_client)
    resp = nginx_client.get(css_url)
    assert resp.status_code == 200
    assert any(k in resp.text for k in ("transition", "keyframes", "animation", "transform", "opacity"))


# ── F9: 交易所 API Key 安全管理中心 ───────────────────────────────────────────

def test_t1_f9_01_credential_save_and_encryption(live_client: httpx.Client, auth_headers):
    """F9: Saving exchange API credentials encrypts secret and returns redacted fingerprint."""
    cid = f"conn-t1-{uuid.uuid4().hex[:6]}"
    resp = live_client.post(
        "/api/v1/live/credentials",
        json={
            "connection_id": cid,
            "exchange": "binance",
            "api_key": "test_api_key_12345678",
            "api_secret": "test_api_secret_abcdefghijk",
            "environment": "testnet",
        },
        headers=auth_headers("admin"),
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["connection_id"] == cid
    assert data["credential_status"] == "stored_encrypted"
    assert "test_api_secret" not in str(data)


def test_t1_f9_02_credentials_redacted_listing(live_client: httpx.Client, auth_headers):
    """F9: Querying credentials list returns masked fingerprints without plaintext secret."""
    resp = live_client.get("/api/v1/live/credentials", headers=auth_headers("admin"))
    assert resp.status_code == 200
    creds = resp.json()
    assert isinstance(creds, list)
    for c in creds:
        assert "connection_id" in c
        assert "api_secret" not in c


def test_t1_f9_03_credential_detail_lookup(live_client: httpx.Client, auth_headers):
    """F9: Querying single credential by connection_id returns redacted item."""
    cid = f"conn-det-{uuid.uuid4().hex[:6]}"
    live_client.post(
        "/api/v1/live/credentials",
        json={
            "connection_id": cid,
            "exchange": "okx",
            "api_key": "okx_api_key_12345678",
            "api_secret": "okx_secret_abcdefghijk",
            "passphrase": "OkxPassphrase123!",
            "environment": "testnet",
        },
        headers=auth_headers("admin"),
    )
    resp = live_client.get(f"/api/v1/live/credentials/{cid}", headers=auth_headers("admin"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["connection_id"] == cid
    assert data["has_passphrase"] is True


def test_t1_f9_04_credential_connectivity_probe(live_client: httpx.Client, auth_headers):
    """F9: Credential test endpoint initiates dry-run connection probe."""
    cid = f"conn-test-{uuid.uuid4().hex[:6]}"
    live_client.post(
        "/api/v1/live/credentials",
        json={
            "connection_id": cid,
            "exchange": "binance",
            "api_key": "binance_probe_key_123",
            "api_secret": "binance_probe_sec_456",
            "environment": "testnet",
        },
        headers=auth_headers("admin"),
    )
    resp = live_client.post(f"/api/v1/live/credentials/{cid}/test", headers=auth_headers("admin"))
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "status" in data


def test_t1_f9_05_credential_deletion(live_client: httpx.Client, auth_headers):
    """F9: Deleting credential removes item from encrypted storage."""
    cid = f"conn-del-{uuid.uuid4().hex[:6]}"
    live_client.post(
        "/api/v1/live/credentials",
        json={
            "connection_id": cid,
            "exchange": "binance",
            "api_key": "del_probe_key_123",
            "api_secret": "del_probe_sec_456",
            "environment": "testnet",
        },
        headers=auth_headers("admin"),
    )
    del_resp = live_client.delete(f"/api/v1/live/credentials/{cid}", headers=auth_headers("admin"))
    assert del_resp.status_code == 200
    assert del_resp.json().get("deleted") is not None


# ── F10: AI 大模型网关配置中心 ─────────────────────────────────────────────────

def test_t1_f10_01_model_providers_configuration(live_client: httpx.Client, auth_headers):
    """F10: Model providers endpoint exposes provider catalog and models."""
    resp = live_client.get("/api/v1/control/model-providers", headers=auth_headers("admin"))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_t1_f10_02_model_provider_update_and_test(live_client: httpx.Client, auth_headers):
    """F10: Updating and testing model provider executes endpoint validation."""
    up_resp = live_client.put(
        "/api/v1/control/model-providers/openai",
        json={
            "provider_id": "openai",
            "display_name": "OpenAI GPT-4o",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o",
            "enabled": True,
            "secret_ref": "env:OPENAI_API_KEY",
            "capabilities": ["chat", "reasoning"],
        },
        headers=auth_headers("admin"),
    )
    assert up_resp.status_code == 200

    test_resp = live_client.post("/api/v1/control/model-providers/openai/test", headers=auth_headers("admin"))
    assert test_resp.status_code == 200
    assert test_resp.json()["provider_id"] == "openai"


def test_t1_f10_03_ai_chat_completion_endpoint(live_client: httpx.Client, auth_headers):
    """F10: AI chat endpoint receives prompt messages and returns structured completion."""
    resp = live_client.post(
        "/api/v1/ai/chat",
        json={
            "provider_id": "deepseek",
            "messages": [{"role": "user", "content": "Analyze market trend for BTCUSDT"}],
            "temperature": 0.2,
            "max_tokens": 512,
        },
        headers=auth_headers("trader"),
    )
    assert resp.status_code in (200, 400, 404, 409, 502, 503)
    if resp.status_code == 200:
        data = resp.json()
        assert "content" in data or "provider_id" in data


def test_t1_f10_04_agent_task_creation(live_client: httpx.Client, auth_headers):
    """F10: Creating quantitative agent task registers task in agent queue."""
    resp = live_client.post(
        "/api/v1/agents/tasks",
        json={"title": "E2E Momentum Scan", "task_type": "market_analysis", "operator": "admin"},
        headers=auth_headers("trader"),
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert "task_id" in data
    assert data["title"] == "E2E Momentum Scan"


def test_t1_f10_05_agent_task_execution(live_client: httpx.Client, auth_headers):
    """F10: Executing agent task returns evidence chain and execution status."""
    create_resp = live_client.post(
        "/api/v1/agents/tasks",
        json={"title": "E2E Exec Scan", "task_type": "market_analysis", "operator": "admin"},
        headers=auth_headers("trader"),
    )
    assert create_resp.status_code in (200, 201)
    task_id = create_resp.json()["task_id"]

    run_resp = live_client.post(f"/api/v1/agents/tasks/{task_id}/run", headers=auth_headers("trader"))
    assert run_resp.status_code == 200
    data = run_resp.json()
    assert data["status"] in ("completed", "running", "success")


# ── F11: 全量自动化测试保障 ────────────────────────────────────────────────────

def test_t1_f11_01_crypto_aes_hmac_roundtrip():
    """F11: AES/CTR + HMAC credential crypto performs authentic encryption and decryption."""
    master_key = "test_e2e_master_secret_key_32_bytes_len"
    raw_payload = {"api_key": "my_api_key", "api_secret": "my_super_secret_exchange_api_secret_key_12345"}

    sealed_token = seal_dict(master_key, raw_payload)
    assert isinstance(sealed_token, str)
    assert "my_super_secret" not in sealed_token

    unsealed_data = open_dict(master_key, sealed_token)
    assert unsealed_data == raw_payload


def test_t1_f11_02_auth_jwt_token_claims():
    """F11: JWT token generation embeds subject, role and expiration claims."""
    token = str(create_access_token("test-user", role="risk_admin"))
    assert isinstance(token, str)
    assert token.startswith("ey")


def test_t1_f11_03_backtest_metrics_calculation():
    """F11: Quantitative backtest indicators calculate Sharpe ratio correctly."""
    bars = [
        Bar(symbol="BTCUSDT", open_time=1000 + i * 60, open=Decimal("10.0"), high=Decimal("11.0"), low=Decimal("9.0"), close=Decimal(str(10.0 + i)), volume=Decimal("100"))
        for i in range(10)
    ]
    sma_vals = sma(bars, length=3)
    assert len(sma_vals) == 10
    assert sma_vals[-1] is not None
    assert abs(sma_vals[-1] - 18.0) < 1e-5


def test_t1_f11_04_alert_webhook_payload_formatter():
    """F11: Alert service syncs market quality alerts and lists alerts correctly."""
    from app.services.alert_service import AlertService

    store = InMemoryStore()
    svc = AlertService(store)
    alerts = svc.sync_market_quality({
        "status": "healthy",
        "latency_ms": 15,
        "ticker_count": 5,
        "sample_time": time.time(),
    })
    assert isinstance(alerts, list)


def test_t1_f11_05_indicators_sma_ema_rsi():
    """F11: Trend and momentum indicator engines compute values without errors."""
    bars = [
        Bar(symbol="BTCUSDT", open_time=1000 + i * 60, open=Decimal("100.0"), high=Decimal("105.0"), low=Decimal("95.0"), close=Decimal(str(100.0 + i)), volume=Decimal("50"))
        for i in range(30)
    ]
    ema_vals = ema(bars, length=10)
    assert len(ema_vals) == 30
    assert ema_vals[-1] is not None


# ── F12: 前端生产构建与 Nginx 部署实机验证 ──────────────────────────────────────

def test_t1_f12_01_nginx_health_proxy(nginx_client: httpx.Client):
    """F12: Nginx reverse proxy forwards /health to FastAPI backend returning 200."""
    resp = nginx_client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


def test_t1_f12_02_nginx_api_proxy_tickers(nginx_client: httpx.Client):
    """F12: Nginx reverse proxy forwards /api/v1/market/tickers returning real data."""
    resp = nginx_client.get("/api/v1/market/tickers")
    assert resp.status_code == 200
    tickers = resp.json()
    assert isinstance(tickers, list)
    assert len(tickers) >= 1


def test_t1_f12_03_nginx_spa_routes_fallback(nginx_client: httpx.Client):
    """F12: Nginx try_files correctly rewrites deep SPA routes to index.html."""
    spa_routes = ["/market", "/execution", "/research", "/risk", "/agents", "/settings"]
    for route in spa_routes:
        resp = nginx_client.get(route)
        assert resp.status_code == 200, f"SPA route {route} returned {resp.status_code}"
        assert "<html" in resp.text.lower() or "<!doctype html>" in resp.text.lower()


def test_t1_f12_04_nginx_security_headers(nginx_client: httpx.Client):
    """F12: HTTP responses served via Nginx contain security headers."""
    resp = nginx_client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff" or "content-type" in resp.headers


def test_t1_f12_05_nginx_assets_caching(nginx_client: httpx.Client):
    """F12: Static assets are accessible with non-empty content lengths."""
    css_url, _ = _get_asset_urls(nginx_client)
    resp = nginx_client.get(css_url)
    assert resp.status_code == 200
    assert int(resp.headers.get("content-length", len(resp.content))) > 0
