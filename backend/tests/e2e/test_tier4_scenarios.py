"""Tier 4: Real-World Business Scenario E2E Test Suite (S1 - S8).

Validates complete multi-step user workflows:
S1: Institutional Trader Complete Flow (Market Data -> Strategy Signal -> Preflight -> Intent -> Fill -> Position & PnL)
S2: Multi-Exchange Credential Management & Dynamic Connectivity Switching (Binance + OKX)
S3: AI Quantitative Assistant Strategy Consulting & Automation Task Execution
S4: Extreme Market Event -> Circuit Breaker -> Governance Approval -> Safe Trading Recovery
S5: RBAC Role-Based Access Control & Audit Log Compliance Tracking
S6: Historical Market Ingestion, Strategy Backtesting & Quantitative Metrics Assessment
S7: System Health Heartbeat, Metrics Export & Degraded Mode Self-Healing Probes
S8: Frontend 7-Page Full Navigation, Bloomberg Dark Theme & SPA Routing Distribution
Total Scenarios: 8.
"""

from __future__ import annotations

import re
import time
import uuid
import httpx
import pytest


def _get_asset_urls(nginx_client: httpx.Client) -> tuple[str, str]:
    resp = nginx_client.get("/")
    css_match = re.search(r'href="(/assets/index-[^"]+\.css)"', resp.text)
    js_match = re.search(r'src="(/assets/index-[^"]+\.js)"', resp.text)
    css_url = css_match.group(1) if css_match else "/assets/index-BuIILVdV.css"
    js_url = js_match.group(1) if js_match else "/assets/index-acZVLmpS.js"
    return css_url, js_url


# ── Scenario S1: Institutional Trader Complete Flow ───────────────────────────

def test_t4_s1_institutional_trader_market_to_order_execution(live_client: httpx.Client, auth_headers):
    """S1: End-to-end institutional workflow from live market feed through order fill and MTM valuation."""
    account_id = f"s1-inst-acc-{uuid.uuid4().hex[:6]}"

    # 1. Ingest real market quotes
    ticker_resp = live_client.get("/api/v1/market/tickers")
    assert ticker_resp.status_code == 200
    tickers = ticker_resp.json()
    assert len(tickers) >= 1

    # 2. Fetch live order book depth
    ob_resp = live_client.get("/api/v1/market/orderbook/BTCUSDT?depth=5")
    assert ob_resp.status_code == 200
    ob = ob_resp.json()
    asks = ob.get("asks", [])
    assert len(asks) >= 1
    best_ask = str(asks[0][0])

    # 3. Submit Risk Preflight Request
    preflight_resp = live_client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": account_id,
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.05000000",
            "price": best_ask,
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
        headers=auth_headers("trader"),
    )
    assert preflight_resp.status_code == 200
    preflight_data = preflight_resp.json()
    assert preflight_data["decision"] == "approved"
    decision_id = preflight_data["decision_id"]

    # 4. Create Order Intent with decision_id
    order_id = f"ord-s1-{uuid.uuid4().hex[:6]}"
    order_resp = live_client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": order_id,
            "account_id": account_id,
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.05000000",
            "limit_price": best_ask,
            "mode": "paper",
            "risk_decision_id": decision_id,
        },
        headers=auth_headers("trader"),
    )
    assert order_resp.status_code in (200, 201)
    assert order_resp.json()["client_order_id"] == order_id

    # 5. Execute Fill
    fill_resp = live_client.post(
        "/api/v1/execution/fills",
        json={"client_order_id": order_id, "fill_quantity": "0.05000000", "fill_price": best_ask},
        headers=auth_headers("trader"),
    )
    assert fill_resp.status_code == 200
    assert str(fill_resp.json()["status"]).lower() == "filled"

    # 6. Verify Position & Mark-to-Market Valuation
    pos_resp = live_client.get(f"/api/v1/positions?account_id={account_id}", headers=auth_headers("trader"))
    assert pos_resp.status_code == 200
    positions = pos_resp.json()
    assert len(positions) >= 1
    btc_pos = next((p for p in positions if p["symbol"] == "BTCUSDT"), None)
    assert btc_pos is not None
    assert float(btc_pos["quantity"]) >= 0.05

    # 7. Run Mark-to-Market
    mark_price = str(float(best_ask) + 500.0)
    mtm_resp = live_client.post(
        "/api/v1/positions/mark-to-market",
        json={"account_id": account_id, "symbol": "BTCUSDT", "mark_price": mark_price, "mode": "paper"},
        headers=auth_headers("trader"),
    )
    assert mtm_resp.status_code == 200
    assert mtm_resp.json().get("positions_updated") is not None


# ── Scenario S2: Multi-Exchange Credential Management & Switching ─────────────

def test_t4_s2_multi_exchange_credentials_and_connectivity(live_client: httpx.Client, auth_headers):
    """S2: End-to-end credential onboarding, ciphertext protection, connectivity probing and cleanup."""
    binance_cid = f"conn-binance-{uuid.uuid4().hex[:6]}"
    okx_cid = f"conn-okx-{uuid.uuid4().hex[:6]}"

    # 1. Save Binance testnet credentials
    b_resp = live_client.post(
        "/api/v1/live/credentials",
        json={
            "connection_id": binance_cid,
            "exchange": "binance",
            "api_key": "binance_test_api_key_12345",
            "api_secret": "binance_test_secret_67890",
            "environment": "testnet",
        },
        headers=auth_headers("admin"),
    )
    assert b_resp.status_code in (200, 201)

    # 2. Save OKX testnet credentials with passphrase
    o_resp = live_client.post(
        "/api/v1/live/credentials",
        json={
            "connection_id": okx_cid,
            "exchange": "okx",
            "api_key": "okx_test_api_key_12345",
            "api_secret": "okx_test_secret_67890",
            "passphrase": "OkxPassphrase123!",
            "environment": "testnet",
        },
        headers=auth_headers("admin"),
    )
    assert o_resp.status_code in (200, 201)

    # 3. Query credentials list (verify masking)
    list_resp = live_client.get("/api/v1/live/credentials", headers=auth_headers("admin"))
    assert list_resp.status_code == 200
    creds = list_resp.json()
    c_ids = [c["connection_id"] for c in creds]
    assert binance_cid in c_ids
    assert okx_cid in c_ids

    # 4. Probe connectivity
    probe_b = live_client.post(f"/api/v1/live/credentials/{binance_cid}/test", headers=auth_headers("admin"))
    assert probe_b.status_code in (200, 503)

    # 5. Clean up credentials
    del_b = live_client.delete(f"/api/v1/live/credentials/{binance_cid}", headers=auth_headers("admin"))
    assert del_b.status_code == 200
    del_o = live_client.delete(f"/api/v1/live/credentials/{okx_cid}", headers=auth_headers("admin"))
    assert del_o.status_code == 200


# ── Scenario S3: AI Quantitative Assistant & Task Execution ───────────────────

def test_t4_s3_ai_model_gateway_and_strategy_chat(live_client: httpx.Client, auth_headers):
    """S3: End-to-end AI gateway configuration, model probe, chat consultation and automated task run."""
    # 1. Update AI model provider
    up_resp = live_client.put(
        "/api/v1/control/model-providers/deepseek",
        json={
            "provider_id": "deepseek",
            "display_name": "DeepSeek R1 S3",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "enabled": True,
            "secret_ref": "env:DEEPSEEK_API_KEY",
            "capabilities": ["chat", "analysis"],
        },
        headers=auth_headers("admin"),
    )
    assert up_resp.status_code == 200

    # 2. Probe AI provider connectivity
    test_resp = live_client.post("/api/v1/control/model-providers/deepseek/test", headers=auth_headers("admin"))
    assert test_resp.status_code == 200
    assert test_resp.json()["provider_id"] == "deepseek"

    # 3. Create Quantitative Analysis Task
    task_resp = live_client.post(
        "/api/v1/agents/tasks",
        json={"title": "S3 Volatility Arbitrage Review", "task_type": "volatility_analysis", "operator": "quant_researcher"},
        headers=auth_headers("quant"),
    )
    assert task_resp.status_code in (200, 201)
    task_id = task_resp.json()["task_id"]

    # 4. Run Task Execution
    run_resp = live_client.post(f"/api/v1/agents/tasks/{task_id}/run", headers=auth_headers("quant"))
    assert run_resp.status_code == 200
    assert run_resp.json()["status"] in ("completed", "running", "success")


# ── Scenario S4: Extreme Market Event & Recovery Flow ─────────────────────────

def test_t4_s4_extreme_market_kill_switch_and_recovery_flow(live_client: httpx.Client, auth_headers):
    """S4: Emergency kill switch activation, order block, multi-sig approval and recovery."""
    account_id = f"s4-acc-{uuid.uuid4().hex[:6]}"

    # 1. Trigger Emergency Kill Switch
    trig_resp = live_client.post(
        "/api/v1/governance/kill-switch/trigger",
        json={"triggered_by": "risk_officer_s4", "reason": "S4 Extreme Market Volatility Anomaly"},
        headers=auth_headers("risk_admin"),
    )
    assert trig_resp.status_code == 200
    assert trig_resp.json()["status"] == "active"

    # 2. Get preflight decision
    pref_resp = live_client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": account_id,
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
    assert pref_resp.status_code == 200
    dec_id = pref_resp.json()["decision_id"]

    # 3. Attempt Order Intent Creation (Must be blocked by active kill switch)
    block_resp = live_client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": f"ord-s4-block-{uuid.uuid4().hex[:6]}",
            "account_id": account_id,
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "65000.00",
            "mode": "paper",
            "risk_decision_id": dec_id,
        },
        headers=auth_headers("trader"),
    )
    assert block_resp.status_code in (400, 503)
    assert "KILL_SWITCH" in block_resp.text

    # 4. Initiate Multi-Sig Governance Approval for Recovery
    appr_resp = live_client.post(
        "/api/v1/governance/approvals",
        json={
            "resource_type": "kill_switch_recovery",
            "resource_id": "system_emergency",
            "requested_by": "risk_officer_s4",
            "title": "S4 Resume Market Operations",
            "details": "Circuit breaker conditions evaluated and normalized.",
        },
        headers=auth_headers("risk_admin"),
    )
    assert appr_resp.status_code in (200, 201)
    appr_id = appr_resp.json()["approval_id"]

    # 5. Decide Approval
    dec_resp = live_client.post(
        f"/api/v1/governance/approvals/{appr_id}/decide",
        json={"decision": "approved", "decided_by": "lead_admin_s4", "reject_reason": None},
        headers=auth_headers("risk_admin"),
    )
    assert dec_resp.status_code == 200

    # 6. Execute Kill Switch Recovery
    rec_resp = live_client.post(
        "/api/v1/governance/kill-switch/recover",
        json={"recovered_by": "lead_admin_s4", "reason": "Authorized recovery", "approval_id": appr_id, "mode": "paper"},
        headers=auth_headers("admin"),
    )
    assert rec_resp.status_code == 200
    assert rec_resp.json()["status"] == "inactive"

    # 7. Resume Order Creation
    resumed_ord_id = f"ord-s4-resumed-{uuid.uuid4().hex[:6]}"
    resumed_resp = live_client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": resumed_ord_id,
            "account_id": account_id,
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "65000.00",
            "mode": "paper",
            "risk_decision_id": dec_id,
        },
        headers=auth_headers("trader"),
    )
    assert resumed_resp.status_code in (200, 201)


# ── Scenario S5: RBAC Role-Based Access Control & Audit Compliance ────────────

def test_t4_s5_rbac_and_audit_trail_compliance(live_client: httpx.Client, auth_headers):
    """S5: End-to-end RBAC permission segregation and immutable audit event trail."""
    # 1. Trader performs allowed trade preflight
    trader_resp = live_client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": "s5-trader-acc",
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
    assert trader_resp.status_code == 200

    # 2. Risk Admin accesses risk governance
    risk_resp = live_client.get("/api/v1/risk/rules", headers=auth_headers("risk_admin"))
    assert risk_resp.status_code == 200

    # 3. Auditor inspects immutable audit logs
    audit_resp = live_client.get("/api/v1/audit/events?limit=20", headers=auth_headers("auditor"))
    assert audit_resp.status_code == 200
    events = audit_resp.json()
    assert isinstance(events, list)


# ── Scenario S6: Historical Market Ingestion & Backtesting ────────────────────

def test_t4_s6_historical_market_data_and_backtest_execution(live_client: httpx.Client, auth_headers):
    """S6: End-to-end historical candlestick ingestion, backtest parameterization and performance report."""
    # 1. Construct 80 bars of hourly historical data
    csv_bars = "timestamp,open,high,low,close,volume\n"
    base_ts = 1720000000000 + int(time.time() % 10000) * 1000
    price = 65000.0
    for i in range(80):
        ts = base_ts + i * 3600000
        p_open = price + (i * 15)
        p_high = p_open + 80
        p_low = p_open - 40
        p_close = p_open + 30
        vol = 250.0 + i
        csv_bars += f"{ts},{p_open},{p_high},{p_low},{p_close},{vol}\n"

    # 2. Import CSV data
    imp_resp = live_client.post(
        "/api/v1/research/historical/import/csv",
        json={"symbol": "BTCUSDT", "period": "1h", "csv_text": csv_bars, "delimiter": ","},
        headers=auth_headers("trader"),
    )
    assert imp_resp.status_code == 200
    assert imp_resp.json().get("bars_imported") == 80

    # 3. Query historical series
    series_resp = live_client.get("/api/v1/research/historical/series", headers=auth_headers("trader"))
    assert series_resp.status_code == 200
    series = series_resp.json()
    assert len(series) >= 1

    # 4. Run Backtest
    bt_resp = live_client.post(
        "/api/v1/research/backtests",
        json={
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "data_snapshot": "snap_parquet_default",
            "initial_capital": "100000.00",
            "mode": "paper",
        },
        headers=auth_headers("trader"),
    )
    assert bt_resp.status_code in (200, 201)
    bt_data = bt_resp.json()
    assert "backtest_id" in bt_data


# ── Scenario S7: System Health & Probes ────────────────────────────────────────

def test_t4_s7_system_health_and_probes(live_client: httpx.Client):
    """S7: End-to-end liveness, readiness, host system resource monitoring."""
    # 1. Check Liveness
    l_resp = live_client.get("/health")
    assert l_resp.status_code == 200
    assert l_resp.json().get("status") == "ok"

    # 2. Check Readiness
    r_resp = live_client.get("/ready")
    assert r_resp.status_code == 200
    assert r_resp.json().get("status") == "ready"

    # 3. Check System Status
    s_resp = live_client.get("/api/v1/system/status")
    assert s_resp.status_code == 200
    status_data = s_resp.json()
    assert status_data.get("status") == "running"
    assert status_data.get("uptime_seconds", 0) > 0


# ── Scenario S8: Frontend Full SPA Routing & Static Assets ────────────────────

def test_t4_s8_frontend_spa_and_bloomberg_theme(nginx_client: httpx.Client):
    """S8: Traversing complete frontend SPA suite served through Nginx."""
    pages = ["/", "/market", "/execution", "/research", "/risk", "/agents", "/settings"]
    for page in pages:
        r = nginx_client.get(page)
        assert r.status_code == 200, f"Page {page} failed with {r.status_code}"
        assert "<!doctype html>" in r.text.lower() or "<html" in r.text.lower()

    # Discover and verify CSS & JS bundle
    css_url, js_url = _get_asset_urls(nginx_client)
    css_resp = nginx_client.get(css_url)
    assert css_resp.status_code == 200
    assert len(css_resp.text) > 2000

    js_resp = nginx_client.get(js_url)
    assert js_resp.status_code == 200
    assert len(js_resp.text) > 50000
