import asyncio
import time
import json
import uuid
import statistics
from datetime import datetime, timezone
import httpx
from pydantic import BaseModel, ValidationError

# Schemas for validation
from app.schemas.market import TickerResponse, OrderBookResponse, TradeResponse, FundingRateResponse, MarketQualityResponse
from app.schemas.risk import PreflightRequest, PreflightResponse
from app.schemas.order import OrderIntentRequest, OrderResponse
from app.schemas.position import MarkToMarketRequest, MarkToMarketResponse
from app.schemas.adapters import CredentialRedactedResponse, CredentialTestResponse, CredentialSaveRequest
from app.schemas.control import (
    ModelProviderResponse, 
    ProviderTestResponse, 
    ModelProviderUpsertRequest,
    ExchangeConnectionResponse,
    ExchangeTestResponse
)

BASE_URL = "http://127.0.0.1:8000"

results = {
    "module_1_market": {},
    "module_2_orders_risk_mtm": {},
    "module_3_credentials": {},
    "module_4_ai_gateway": {},
    "module_5_control_exchanges": {},
    "module_6_stress_and_edge": {},
    "summary": {
        "total_tests": 0,
        "passed_tests": 0,
        "failed_tests": 0,
        "verdict": "PENDING"
    }
}

def record_test(module, test_name, passed, details=None, latency_ms=None):
    results["summary"]["total_tests"] += 1
    if passed:
        results["summary"]["passed_tests"] += 1
    else:
        results["summary"]["failed_tests"] += 1
    
    results[module][test_name] = {
        "passed": passed,
        "latency_ms": latency_ms,
        "details": details or {}
    }
    status_str = "PASS" if passed else "FAIL"
    lat_str = f" ({latency_ms:.1f}ms)" if latency_ms is not None else ""
    print(f"[{status_str}] {module} -> {test_name}{lat_str}")
    if not passed and details:
        print(f"       Details: {details}")

async def run_market_tests(client: httpx.AsyncClient):
    print("\n=======================================================")
    print(" MODULE 1: MARKET DATA & 20-LEVEL ORDERBOOK STRESS")
    print("=======================================================")
    
    # 1.1 Tickers
    t0 = time.perf_counter()
    r = await client.get("/api/v1/market/tickers")
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        data = r.json()
        try:
            validated = [TickerResponse.model_validate(item) for item in data]
            symbols = [t.symbol for t in validated]
            has_major = all(s in symbols for s in ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
            all_positive = all(float(t.last_price) > 0 for t in validated)
            record_test("module_1_market", "1.1_tickers_schema_and_values", 
                        has_major and all_positive, 
                        {"count": len(validated), "symbols": symbols, "sources": list(set(t.source for t in validated))},
                        latency_ms=lat)
        except Exception as e:
            record_test("module_1_market", "1.1_tickers_schema_and_values", False, {"error": str(e)}, latency_ms=lat)
    else:
        record_test("module_1_market", "1.1_tickers_schema_and_values", False, {"status": r.status_code, "text": r.text}, latency_ms=lat)

    # 1.2 20-Level Orderbook for multiple symbols
    symbols_to_test = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"]
    for sym in symbols_to_test:
        t0 = time.perf_counter()
        r = await client.get(f"/api/v1/market/orderbook/{sym}?depth=20")
        lat = (time.perf_counter() - t0) * 1000
        if r.status_code == 200:
            data = r.json()
            try:
                ob = OrderBookResponse.model_validate(data)
                bids = ob.bids
                asks = ob.asks
                
                depth_ok = (len(bids) == 20 and len(asks) == 20)
                bids_desc = all(float(bids[i][0]) >= float(bids[i+1][0]) for i in range(len(bids)-1))
                asks_asc = all(float(asks[i][0]) <= float(asks[i+1][0]) for i in range(len(asks)-1))
                
                best_bid = float(bids[0][0]) if bids else 0
                best_ask = float(asks[0][0]) if asks else float("inf")
                no_crossed = best_ask > best_bid
                qty_ok = all(float(b[1]) > 0 for b in bids) and all(float(a[1]) > 0 for a in asks)
                
                all_ok = depth_ok and bids_desc and asks_asc and no_crossed and qty_ok
                record_test("module_1_market", f"1.2_orderbook_20levels_{sym}", all_ok, {
                    "symbol": sym,
                    "depth_bids": len(bids),
                    "depth_asks": len(asks),
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "spread": best_ask - best_bid,
                    "bids_descending": bids_desc,
                    "asks_ascending": asks_asc,
                    "source": ob.source
                }, latency_ms=lat)
            except Exception as e:
                record_test("module_1_market", f"1.2_orderbook_20levels_{sym}", False, {"error": str(e)}, latency_ms=lat)
        else:
            record_test("module_1_market", f"1.2_orderbook_20levels_{sym}", False, {"status": r.status_code, "text": r.text}, latency_ms=lat)

    # 1.3 Orderbook depth boundary check (depth=25 should fail with 422)
    t0 = time.perf_counter()
    r = await client.get("/api/v1/market/orderbook/BTCUSDT?depth=25")
    lat = (time.perf_counter() - t0) * 1000
    record_test("module_1_market", "1.3_orderbook_depth_bound_ge_le", r.status_code == 422, {"status": r.status_code}, latency_ms=lat)

    # 1.4 Real-time Trades
    t0 = time.perf_counter()
    r = await client.get("/api/v1/market/trades/BTCUSDT?limit=20")
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        try:
            trades = [TradeResponse.model_validate(item) for item in r.json()]
            trades_ok = len(trades) > 0 and all(float(t.price) > 0 and float(t.quantity) > 0 for t in trades)
            record_test("module_1_market", "1.4_trades_stream", trades_ok, {"count": len(trades), "sample": [trades[0].model_dump()] if trades else []}, latency_ms=lat)
        except Exception as e:
            record_test("module_1_market", "1.4_trades_stream", False, {"error": str(e)}, latency_ms=lat)
    else:
        record_test("module_1_market", "1.4_trades_stream", False, {"status": r.status_code, "text": r.text}, latency_ms=lat)

    # 1.5 Funding Rates
    t0 = time.perf_counter()
    r = await client.get("/api/v1/market/funding")
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        try:
            rates = [FundingRateResponse.model_validate(item) for item in r.json()]
            rates_ok = len(rates) > 0 and all(f.symbol and f.rate for f in rates)
            record_test("module_1_market", "1.5_funding_rates", rates_ok, {"count": len(rates), "symbols": [f.symbol for f in rates]}, latency_ms=lat)
        except Exception as e:
            record_test("module_1_market", "1.5_funding_rates", False, {"error": str(e)}, latency_ms=lat)
    else:
        record_test("module_1_market", "1.5_funding_rates", False, {"status": r.status_code, "text": r.text}, latency_ms=lat)

    # 1.6 High Frequency Concurrency Burst (102 parallel requests)
    print("\n--- Running 102-request Market Data Burst ---")
    urls = [
        "/api/v1/market/tickers",
        "/api/v1/market/orderbook/BTCUSDT?depth=20",
        "/api/v1/market/orderbook/ETHUSDT?depth=20",
        "/api/v1/market/orderbook/SOLUSDT?depth=20",
        "/api/v1/market/trades/BTCUSDT?limit=20",
        "/api/v1/market/funding"
    ] * 17  # 102 requests
    
    async def fetch_one(url):
        start = time.perf_counter()
        resp = await client.get(url)
        elapsed = (time.perf_counter() - start) * 1000
        return resp.status_code, elapsed

    t_burst_start = time.perf_counter()
    burst_results = await asyncio.gather(*(fetch_one(u) for u in urls), return_exceptions=True)
    t_burst_total = (time.perf_counter() - t_burst_start) * 1000
    
    successes = [res for res in burst_results if isinstance(res, tuple) and res[0] == 200]
    latencies = [res[1] for res in burst_results if isinstance(res, tuple)]
    
    p50 = statistics.median(latencies) if latencies else 0
    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies or [0])
    p99 = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else max(latencies or [0])
    
    burst_passed = len(successes) == len(urls)
    record_test("module_1_market", "1.6_high_frequency_100_burst", burst_passed, {
        "total_requests": len(urls),
        "successful_requests": len(successes),
        "total_burst_wall_time_ms": t_burst_total,
        "rps": len(urls) / (t_burst_total / 1000),
        "latency_min_ms": min(latencies) if latencies else 0,
        "latency_p50_ms": p50,
        "latency_p95_ms": p95,
        "latency_p99_ms": p99,
        "latency_max_ms": max(latencies) if latencies else 0
    })

async def run_order_risk_mtm_tests(client: httpx.AsyncClient):
    print("\n=======================================================")
    print(" MODULE 2: RISK PREFLIGHT, ORDER INTENTS & MTM")
    print("=======================================================")
    
    # 2.1 Valid Risk Preflight
    preflight_payload = {
        "account_id": "paper-main",
        "symbol": "BTCUSDT",
        "side": "buy",
        "quantity": "0.05",
        "price": "65000.0",
        "strategy_id": "challenger-strat-01",
        "strategy_version": "v1.0",
        "mode": "paper"
    }
    t0 = time.perf_counter()
    r = await client.post("/api/v1/risk/preflight", json=preflight_payload)
    lat = (time.perf_counter() - t0) * 1000
    decision_id = None
    if r.status_code == 200:
        data = r.json()
        try:
            resp = PreflightResponse.model_validate(data)
            decision_id = resp.decision_id
            pf_ok = (resp.decision == "approved" and bool(resp.decision_id) and len(resp.rules_checked) > 0)
            record_test("module_2_orders_risk_mtm", "2.1_risk_preflight_approved", pf_ok, {
                "decision": resp.decision,
                "decision_id": resp.decision_id,
                "remaining_budget": resp.remaining_risk_budget,
                "rules_checked_count": len(resp.rules_checked)
            }, latency_ms=lat)
        except Exception as e:
            record_test("module_2_orders_risk_mtm", "2.1_risk_preflight_approved", False, {"error": str(e)}, latency_ms=lat)
    else:
        record_test("module_2_orders_risk_mtm", "2.1_risk_preflight_approved", False, {"status": r.status_code, "text": r.text}, latency_ms=lat)

    # 2.2 Risk Preflight Rejection (Extreme Oversized Order)
    bad_preflight = {
        "account_id": "paper-main",
        "symbol": "BTCUSDT",
        "side": "buy",
        "quantity": "99999999.0",
        "price": "1000000.0",
        "strategy_id": "challenger-strat-01",
        "strategy_version": "v1.0",
        "mode": "paper"
    }
    t0 = time.perf_counter()
    r = await client.post("/api/v1/risk/preflight", json=bad_preflight)
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        data = r.json()
        resp = PreflightResponse.model_validate(data)
        rejected_ok = (resp.decision == "rejected" and resp.reject_reason is not None)
        record_test("module_2_orders_risk_mtm", "2.2_risk_preflight_oversized_rejection", rejected_ok, {
            "decision": resp.decision,
            "reject_reason": resp.reject_reason
        }, latency_ms=lat)
    elif r.status_code in [400, 422]:
        record_test("module_2_orders_risk_mtm", "2.2_risk_preflight_oversized_rejection", True, {"status": r.status_code, "message": "Rejected via validation"}, latency_ms=lat)
    else:
        record_test("module_2_orders_risk_mtm", "2.2_risk_preflight_oversized_rejection", False, {"status": r.status_code}, latency_ms=lat)

    # 2.3 Order Intent Creation with valid decision_id
    client_order_id = f"challenger-ord-{uuid.uuid4().hex[:8]}"
    order_payload = {
        "client_order_id": client_order_id,
        "account_id": "paper-main",
        "strategy_id": "challenger-strat-01",
        "strategy_version": "v1.0",
        "symbol": "BTCUSDT",
        "market_type": "spot",
        "side": "buy",
        "order_type": "limit",
        "quantity": "0.05",
        "limit_price": "65000.0",
        "mode": "paper",
        "risk_decision_id": decision_id or "dummy-decision-id"
    }
    t0 = time.perf_counter()
    r = await client.post("/api/v1/orders/intents", json=order_payload)
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        data = r.json()
        try:
            ord_resp = OrderResponse.model_validate(data)
            valid_statuses = ["new", "submitted", "accepted", "filled", "pending_submission"]
            ord_ok = (ord_resp.client_order_id == client_order_id and ord_resp.status in valid_statuses)
            record_test("module_2_orders_risk_mtm", "2.3_order_intent_creation", ord_ok, {
                "client_order_id": ord_resp.client_order_id,
                "status": ord_resp.status,
                "filled_quantity": ord_resp.filled_quantity,
                "average_price": ord_resp.average_price
            }, latency_ms=lat)
        except Exception as e:
            record_test("module_2_orders_risk_mtm", "2.3_order_intent_creation", False, {"error": str(e)}, latency_ms=lat)
    else:
        record_test("module_2_orders_risk_mtm", "2.3_order_intent_creation", False, {"status": r.status_code, "text": r.text}, latency_ms=lat)

    # 2.4 Query Orders to verify persistence
    t0 = time.perf_counter()
    r = await client.get("/api/v1/orders?account_id=paper-main")
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        orders = r.json()
        found = any(o.get("client_order_id") == client_order_id for o in orders)
        record_test("module_2_orders_risk_mtm", "2.4_order_persistence_query", found, {"found": found, "total_orders": len(orders)}, latency_ms=lat)
    else:
        record_test("module_2_orders_risk_mtm", "2.4_order_persistence_query", False, {"status": r.status_code}, latency_ms=lat)

    # 2.5 Duplicate Order ID check (idempotency/conflict)
    t0 = time.perf_counter()
    r = await client.post("/api/v1/orders/intents", json=order_payload)
    lat = (time.perf_counter() - t0) * 1000
    dup_handled = r.status_code in [200, 400, 409, 422]
    record_test("module_2_orders_risk_mtm", "2.5_duplicate_order_conflict_check", dup_handled, {"status": r.status_code}, latency_ms=lat)

    # 2.6 Mark-to-Market (MTM) calculation
    mtm_payload = {
        "account_id": "paper-main",
        "symbol": "BTCUSDT",
        "mark_price": "71500.50",
        "mode": "paper",
        "idempotency_key": f"mtm-key-{uuid.uuid4().hex[:6]}"
    }
    t0 = time.perf_counter()
    r = await client.post("/api/v1/positions/mark-to-market", json=mtm_payload)
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        data = r.json()
        try:
            mtm_resp = MarkToMarketResponse.model_validate(data)
            mtm_ok = (mtm_resp.account_id == "paper-main" and mtm_resp.symbol == "BTCUSDT" and mtm_resp.mark_price == "71500.50")
            record_test("module_2_orders_risk_mtm", "2.6_position_mtm_calculation", mtm_ok, {
                "positions_updated": mtm_resp.positions_updated,
                "updates": mtm_resp.updates,
                "mark_price": mtm_resp.mark_price
            }, latency_ms=lat)
        except Exception as e:
            record_test("module_2_orders_risk_mtm", "2.6_position_mtm_calculation", False, {"error": str(e)}, latency_ms=lat)
    else:
        record_test("module_2_orders_risk_mtm", "2.6_position_mtm_calculation", False, {"status": r.status_code, "text": r.text}, latency_ms=lat)

    # 2.7 Positions List Query
    t0 = time.perf_counter()
    r = await client.get("/api/v1/positions?account_id=paper-main")
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        positions = r.json()
        record_test("module_2_orders_risk_mtm", "2.7_positions_list_query", isinstance(positions, list), {"count": len(positions), "positions": positions}, latency_ms=lat)
    else:
        record_test("module_2_orders_risk_mtm", "2.7_positions_list_query", False, {"status": r.status_code}, latency_ms=lat)

async def run_credential_tests(client: httpx.AsyncClient):
    print("\n=======================================================")
    print(" MODULE 3: EXCHANGE CREDENTIALS SECURITY & ENCRYPTION")
    print("=======================================================")
    
    # 3.1 Initial List & Masking check
    t0 = time.perf_counter()
    r = await client.get("/api/v1/live/credentials")
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        raw_items = r.json()
        try:
            creds = [CredentialRedactedResponse.model_validate(c) for c in raw_items]
            # Ensure no secret keys ("api_secret", "raw_secret") are leaked in dict keys
            no_secrets_leaked = not any("api_secret" in item or "api_key" in item for item in raw_items)
            fingerprints_ok = all(bool(c.credential_fingerprint) for c in creds if c.credential_status == "stored_encrypted")
            record_test("module_3_credentials", "3.1_credentials_list_and_masking", no_secrets_leaked, {
                "count": len(creds),
                "connections": [c.connection_id for c in creds],
                "fingerprints_verified": fingerprints_ok,
                "no_secrets_leaked": no_secrets_leaked
            }, latency_ms=lat)
        except Exception as e:
            record_test("module_3_credentials", "3.1_credentials_list_and_masking", False, {"error": str(e)}, latency_ms=lat)
    else:
        record_test("module_3_credentials", "3.1_credentials_list_and_masking", False, {"status": r.status_code}, latency_ms=lat)

    # 3.2 Save Test Credential (Binance Testnet)
    bin_conn_id = f"challenger-bin-{uuid.uuid4().hex[:6]}"
    bin_payload = {
        "connection_id": bin_conn_id,
        "exchange": "binance",
        "api_key": "AKIA_CHALLENGER_TEST_BIN_01",
        "api_secret": "SEC_CHALLENGER_SUPER_SECRET_12345",
        "environment": "testnet",
        "base_url": "https://testnet.binance.vision"
    }
    t0 = time.perf_counter()
    r = await client.post("/api/v1/live/credentials", json=bin_payload)
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        data = r.json()
        try:
            resp = CredentialRedactedResponse.model_validate(data)
            saved_ok = (resp.connection_id == bin_conn_id and resp.exchange == "binance" and resp.environment == "testnet")
            record_test("module_3_credentials", "3.2_save_credential_binance", saved_ok, {
                "connection_id": resp.connection_id,
                "fingerprint": resp.credential_fingerprint,
                "status": resp.credential_status
            }, latency_ms=lat)
        except Exception as e:
            record_test("module_3_credentials", "3.2_save_credential_binance", False, {"error": str(e)}, latency_ms=lat)
    else:
        record_test("module_3_credentials", "3.2_save_credential_binance", False, {"status": r.status_code, "text": r.text}, latency_ms=lat)

    # 3.3 Save Test Credential with Passphrase (OKX Testnet)
    okx_conn_id = f"challenger-okx-{uuid.uuid4().hex[:6]}"
    okx_payload = {
        "connection_id": okx_conn_id,
        "exchange": "okx",
        "api_key": "AKIA_CHALLENGER_TEST_OKX_01",
        "api_secret": "SEC_CHALLENGER_OKX_SECRET_98765",
        "passphrase": "PASS_CHALLENGER_PHRASE",
        "environment": "testnet",
        "base_url": "https://www.okx.com"
    }
    t0 = time.perf_counter()
    r = await client.post("/api/v1/live/credentials", json=okx_payload)
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        data = r.json()
        resp = CredentialRedactedResponse.model_validate(data)
        okx_ok = (resp.connection_id == okx_conn_id and resp.has_passphrase is True)
        record_test("module_3_credentials", "3.3_save_credential_okx_passphrase", okx_ok, {
            "connection_id": resp.connection_id,
            "has_passphrase": resp.has_passphrase
        }, latency_ms=lat)
    else:
        record_test("module_3_credentials", "3.3_save_credential_okx_passphrase", False, {"status": r.status_code}, latency_ms=lat)

    # 3.4 Dry-run Connectivity Test
    t0 = time.perf_counter()
    r = await client.post(f"/api/v1/live/credentials/{bin_conn_id}/test")
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        data = r.json()
        try:
            test_resp = CredentialTestResponse.model_validate(data)
            test_ok = (test_resp.connection_id == bin_conn_id and test_resp.status in ["ok", "failed", "tested", "ready", "connected"])
            record_test("module_3_credentials", "3.4_credential_dryrun_connectivity_test", test_ok, {
                "connection_id": test_resp.connection_id,
                "status": test_resp.status,
                "message": test_resp.message
            }, latency_ms=lat)
        except Exception as e:
            record_test("module_3_credentials", "3.4_credential_dryrun_connectivity_test", False, {"error": str(e)}, latency_ms=lat)
    else:
        record_test("module_3_credentials", "3.4_credential_dryrun_connectivity_test", False, {"status": r.status_code}, latency_ms=lat)

    # 3.5 Cleanup Test Credentials
    r_del1 = await client.delete(f"/api/v1/live/credentials/{bin_conn_id}")
    r_del2 = await client.delete(f"/api/v1/live/credentials/{okx_conn_id}")
    del_ok = (r_del1.status_code in [200, 204] and r_del2.status_code in [200, 204])
    record_test("module_3_credentials", "3.5_cleanup_test_credentials", del_ok, {
        "bin_del_status": r_del1.status_code,
        "okx_del_status": r_del2.status_code
    })

async def run_ai_gateway_tests(client: httpx.AsyncClient):
    print("\n=======================================================")
    print(" MODULE 4: AI MODEL GATEWAY PROVIDER MANAGEMENT")
    print("=======================================================")
    
    # 4.1 List Model Providers
    t0 = time.perf_counter()
    r = await client.get("/api/v1/control/model-providers")
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        data = r.json()
        try:
            providers = [ModelProviderResponse.model_validate(p) for p in data]
            prov_ok = len(providers) > 0
            record_test("module_4_ai_gateway", "4.1_model_providers_list", prov_ok, {
                "count": len(providers),
                "provider_ids": [p.provider_id for p in providers],
                "statuses": {p.provider_id: p.status for p in providers}
            }, latency_ms=lat)
        except Exception as e:
            record_test("module_4_ai_gateway", "4.1_model_providers_list", False, {"error": str(e)}, latency_ms=lat)
    else:
        record_test("module_4_ai_gateway", "4.1_model_providers_list", False, {"status": r.status_code}, latency_ms=lat)

    # 4.2 Upsert Model Provider (OpenAI / DeepSeek config)
    upsert_payload = {
        "provider_id": "openai",
        "display_name": "OpenAI GPT-4o Gateway",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "secret_ref": "env://OPENAI_API_KEY",
        "enabled": True,
        "capabilities": ["chat", "quant_analysis"]
    }
    t0 = time.perf_counter()
    r = await client.put("/api/v1/control/model-providers/openai", json=upsert_payload)
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        data = r.json()
        try:
            p_resp = ModelProviderResponse.model_validate(data)
            upsert_ok = (p_resp.provider_id == "openai" and p_resp.enabled is True and p_resp.model == "gpt-4o")
            record_test("module_4_ai_gateway", "4.2_model_provider_upsert", upsert_ok, {
                "provider_id": p_resp.provider_id,
                "display_name": p_resp.display_name,
                "runtime_ready": p_resp.runtime_ready,
                "status": p_resp.status
            }, latency_ms=lat)
        except Exception as e:
            record_test("module_4_ai_gateway", "4.2_model_provider_upsert", False, {"error": str(e)}, latency_ms=lat)
    else:
        record_test("module_4_ai_gateway", "4.2_model_provider_upsert", False, {"status": r.status_code, "text": r.text}, latency_ms=lat)

    # 4.3 Model Provider Connectivity Test
    t0 = time.perf_counter()
    r = await client.post("/api/v1/control/model-providers/openai/test")
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        data = r.json()
        try:
            t_resp = ProviderTestResponse.model_validate(data)
            valid_prov_statuses = ["secret_resolved", "reference_configured", "not_configured", "disabled", "ready", "ok", "tested", "degraded"]
            test_ok = (t_resp.provider_id == "openai" and t_resp.status in valid_prov_statuses)
            record_test("module_4_ai_gateway", "4.3_model_provider_test_connectivity", test_ok, {
                "provider_id": t_resp.provider_id,
                "status": t_resp.status,
                "runtime_ready": t_resp.runtime_ready,
                "message": t_resp.message
            }, latency_ms=lat)
        except Exception as e:
            record_test("module_4_ai_gateway", "4.3_model_provider_test_connectivity", False, {"error": str(e)}, latency_ms=lat)
    else:
        record_test("module_4_ai_gateway", "4.3_model_provider_test_connectivity", False, {"status": r.status_code}, latency_ms=lat)

    # 4.4 Non-existent Model Provider Test (Should handle gracefully)
    t0 = time.perf_counter()
    r = await client.post("/api/v1/control/model-providers/non-existent-prov-99/test")
    lat = (time.perf_counter() - t0) * 1000
    record_test("module_4_ai_gateway", "4.4_model_provider_nonexistent_handling", r.status_code in [400, 404, 422], {"status": r.status_code}, latency_ms=lat)

async def run_control_exchange_tests(client: httpx.AsyncClient):
    print("\n=======================================================")
    print(" MODULE 5: CONTROL EXCHANGES DEFECT VERIFICATION (F5)")
    print("=======================================================")
    
    # 5.1 List Exchange Connections (Check F5 fix for KeyError: 'adapter_name')
    t0 = time.perf_counter()
    r = await client.get("/api/v1/control/exchanges")
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        data = r.json()
        try:
            exchanges = [ExchangeConnectionResponse.model_validate(item) for item in data]
            has_paper = any(e.connection_id == "paper-paper" or e.adapter_name == "paper" for e in exchanges)
            record_test("module_5_control_exchanges", "5.1_control_exchanges_listing_f5", has_paper, {
                "count": len(exchanges),
                "exchanges": [e.connection_id for e in exchanges]
            }, latency_ms=lat)
        except Exception as e:
            record_test("module_5_control_exchanges", "5.1_control_exchanges_listing_f5", False, {"error": str(e)}, latency_ms=lat)
    else:
        record_test("module_5_control_exchanges", "5.1_control_exchanges_listing_f5", False, {"status": r.status_code, "text": r.text}, latency_ms=lat)

    # 5.2 Test Paper Exchange Connection
    t0 = time.perf_counter()
    r = await client.post("/api/v1/control/exchanges/paper-paper/test")
    lat = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        data = r.json()
        try:
            t_resp = ExchangeTestResponse.model_validate(data)
            record_test("module_5_control_exchanges", "5.2_control_exchanges_test_paper", t_resp.runtime_ready is True, {
                "connection_id": t_resp.connection_id,
                "status": t_resp.status,
                "runtime_ready": t_resp.runtime_ready,
                "message": t_resp.message
            }, latency_ms=lat)
        except Exception as e:
            record_test("module_5_control_exchanges", "5.2_control_exchanges_test_paper", False, {"error": str(e)}, latency_ms=lat)
    else:
        record_test("module_5_control_exchanges", "5.2_control_exchanges_test_paper", False, {"status": r.status_code}, latency_ms=lat)

async def run_stress_and_edge_tests(client: httpx.AsyncClient):
    print("\n=======================================================")
    print(" MODULE 6: SECURITY, EDGE CASES & RESILIENCE")
    print("=======================================================")
    
    # 6.1 SQL Injection string in market orderbook symbol parameter
    t0 = time.perf_counter()
    r = await client.get("/api/v1/market/orderbook/BTCUSDT%27%20OR%201=1--?depth=5")
    lat = (time.perf_counter() - t0) * 1000
    record_test("module_6_stress_and_edge", "6.1_sqli_resilience_symbol", r.status_code in [400, 404, 422], {"status": r.status_code}, latency_ms=lat)

    # 6.2 Malformed JSON in Order Intent
    t0 = time.perf_counter()
    r = await client.post("/api/v1/orders/intents", content="{bad_json_string: true", headers={"Content-Type": "application/json"})
    lat = (time.perf_counter() - t0) * 1000
    record_test("module_6_stress_and_edge", "6.2_malformed_json_order_intent", r.status_code in [400, 422], {"status": r.status_code}, latency_ms=lat)

    # 6.3 Empty payload in Risk Preflight
    t0 = time.perf_counter()
    r = await client.post("/api/v1/risk/preflight", json={})
    lat = (time.perf_counter() - t0) * 1000
    record_test("module_6_stress_and_edge", "6.3_empty_payload_risk_preflight", r.status_code == 422, {"status": r.status_code}, latency_ms=lat)

    # 6.4 High Concurrency Mixed Operations (60 concurrent diverse tasks)
    print("\n--- Running 60-task Mixed Full Pipeline Concurrency Test ---")
    async def mixed_task(idx):
        if idx % 5 == 0:
            return await client.get("/api/v1/market/tickers")
        elif idx % 5 == 1:
            return await client.get("/api/v1/market/orderbook/BTCUSDT?depth=20")
        elif idx % 5 == 2:
            return await client.post("/api/v1/risk/preflight", json={
                "account_id": "paper-main",
                "symbol": "BTCUSDT",
                "side": "buy",
                "quantity": "0.01",
                "price": "65000.0",
                "strategy_id": f"strat-{idx}",
                "strategy_version": "v1.0",
                "mode": "paper"
            })
        elif idx % 5 == 3:
            return await client.get("/api/v1/control/model-providers")
        else:
            return await client.get("/api/v1/control/exchanges")

    t_mix_start = time.perf_counter()
    mix_resps = await asyncio.gather(*(mixed_task(i) for i in range(60)), return_exceptions=True)
    t_mix_total = (time.perf_counter() - t_mix_start) * 1000
    
    mix_successes = [r for r in mix_resps if not isinstance(r, Exception) and r.status_code in [200, 201]]
    mix_ok = len(mix_successes) == 60
    record_test("module_6_stress_and_edge", "6.4_mixed_concurrency_pipeline", mix_ok, {
        "total_tasks": 60,
        "successful_tasks": len(mix_successes),
        "wall_time_ms": t_mix_total,
        "throughput_rps": 60 / (t_mix_total / 1000)
    })

async def main():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        await run_market_tests(client)
        await run_order_risk_mtm_tests(client)
        await run_credential_tests(client)
        await run_ai_gateway_tests(client)
        await run_control_exchange_tests(client)
        await run_stress_and_edge_tests(client)
        
    s = results["summary"]
    total = s["total_tests"]
    passed = s["passed_tests"]
    failed = s["failed_tests"]
    
    if failed == 0 and total > 0:
        results["summary"]["verdict"] = "APPROVE"
    else:
        results["summary"]["verdict"] = "REJECT"
        
    print("\n=======================================================")
    print(f" FINAL SUMMARY: {passed}/{total} PASSED ({failed} FAILED)")
    print(f" EMPIRICAL VERDICT: {results['summary']['verdict']}")
    print("=======================================================")
    
    with open("/root/abc-project/backend/challenger_stress_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("Saved results to /root/abc-project/backend/challenger_stress_results.json")

if __name__ == "__main__":
    asyncio.run(main())
