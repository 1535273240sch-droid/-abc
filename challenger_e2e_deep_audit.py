import os
import sys
import json
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

BASE_URL = "http://127.0.0.1"

print("=" * 80)
print("  EMPIRICAL CHALLENGER 2: COMPREHENSIVE PRODUCTION E2E & DEPLOYMENT AUDIT")
print(f"  Target: {BASE_URL} (Nginx Port 80)")
print("=" * 80)

audit_results = {
    "spa_routes": [],
    "static_assets": [],
    "api_proxy": [],
    "concurrency": {},
    "verdict": "UNKNOWN",
    "failures": []
}

def record_check(category, name, passed, details=""):
    item = {"name": name, "passed": passed, "details": details}
    if category in audit_results:
        audit_results[category].append(item)
    if not passed:
        audit_results["failures"].append(f"[{category}] {name}: {details}")
    status_str = "PASS" if passed else "FAIL"
    print(f"  [{status_str}] {name:<48} | {details}")

# 1. Test 7 Main SPA Routes + Sub-routes + Fallback
print("\n--- [1] Frontend SPA Routes Verification (Nginx port 80) ---")
spa_routes = [
    "/",
    "/dashboard",
    "/market",
    "/execution",
    "/research",
    "/risk",
    "/agents",
    "/settings",
    "/dashboard/overview",
    "/market/BTCUSDT",
    "/settings/exchanges",
    "/non-existent-spa-route-test-404-fallback"
]

for route in spa_routes:
    url = f"{BASE_URL}{route}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read().decode("utf-8", errors="ignore")
            is_valid_html = "<div id=\"root\"></div>" in body and "<!doctype html>" in body.lower()
            passed = (status == 200) and ("text/html" in content_type) and is_valid_html
            record_check("spa_routes", route, passed, f"Status={status}, Type={content_type}, Size={len(body)}B, HasRootDiv={is_valid_html}")
    except Exception as e:
        record_check("spa_routes", route, False, f"Exception: {e}")

# 2. Test Static Assets
print("\n--- [2] Static Assets Verification (Port 80) ---")
static_assets = [
    ("/assets/index-oAgbEC-V.js", "application/javascript"),
    ("/assets/index-DiyA03G2.css", "text/css")
]

for path, expected_type in static_assets:
    url = f"{BASE_URL}{path}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            content_length = int(resp.headers.get("Content-Length", len(resp.read())))
            passed = (status == 200) and (expected_type in content_type) and (content_length > 1000)
            record_check("static_assets", path, passed, f"Status={status}, Type={content_type}, Length={content_length}B")
    except Exception as e:
        record_check("static_assets", path, False, f"Exception: {e}")

# 3. Test API Proxy Endpoints across All Functional Modules
print("\n--- [3] API Proxy & Reverse Routing (/api/v1/* & /health & /docs) ---")
api_endpoints = [
    # Health & System
    ("/health", ["status"]),
    ("/health/ready", ["status"]),
    ("/ready", ["status"]),
    ("/info", ["app_name", "app_version"]),
    ("/docs", []),
    ("/openapi.json", ["openapi", "paths"]),
    ("/api/v1/system/status", ["app_name", "status"]),
    # Market Data
    ("/api/v1/market/symbols", None),
    ("/api/v1/market/tickers", None),
    ("/api/v1/market/quality", ["status"]),
    ("/api/v1/market/orderbook/BTCUSDT", ["symbol", "bids", "asks"]),
    ("/api/v1/market/trades/BTCUSDT", None),
    ("/api/v1/market/funding", None),
    # Orders & Positions & Execution
    ("/api/v1/orders", None),
    ("/api/v1/positions", None),
    ("/api/v1/execution/reconciliation", None),
    ("/api/v1/adapters", None),
    ("/api/v1/portfolio/targets", None),
    # Strategy & Research
    ("/api/v1/strategies", None),
    ("/api/v1/strategies/runs", None),
    ("/api/v1/research/backtests", None),
    ("/api/v1/research/historical/series", None),
    ("/api/v1/framework/strategies", None),
    ("/api/v1/framework/klines/status", None),
    # Risk & Governance
    ("/api/v1/risk/rules", None),
    ("/api/v1/risk/circuit-breakers", None),
    ("/api/v1/governance/kill-switch", ["status"]),
    ("/api/v1/governance/approvals", None),
    # Agents & Alerts & Control & Live
    ("/api/v1/agents/tasks", None),
    ("/api/v1/alerts/status", None),
    ("/api/v1/control/exchanges", None),
    ("/api/v1/control/model-providers", None),
    ("/api/v1/live/credentials", None),
    ("/api/v1/live/gate/status", None),
    ("/api/v1/live/risk/status", None),
    ("/api/v1/audit/events", None)
]

for ep, req_keys in api_endpoints:
    url = f"{BASE_URL}{ep}"
    try:
        req = urllib.request.Request(url)
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=5) as resp:
            t1 = time.perf_counter()
            latency_ms = round((t1 - t0) * 1000, 2)
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            req_id = resp.headers.get("X-Request-ID", "N/A")
            raw_body = resp.read()
            
            valid_payload = True
            key_info = ""
            if "application/json" in content_type:
                data = json.loads(raw_body)
                if isinstance(data, dict):
                    key_info = f"Keys={list(data.keys())[:5]}"
                    if req_keys:
                        for k in req_keys:
                            if k not in data:
                                valid_payload = False
                                key_info += f" (MISSING '{k}')"
                elif isinstance(data, list):
                    key_info = f"ItemsCount={len(data)}"
            elif "text/html" in content_type and ep == "/docs":
                key_info = f"SwaggerUI HTML={len(raw_body)}B"
            
            passed = (status == 200) and valid_payload
            record_check("api_proxy", ep, passed, f"Status={status}, Latency={latency_ms}ms, ReqID={req_id[:8]}.., {key_info}")
    except Exception as e:
        record_check("api_proxy", ep, False, f"Exception: {e}")

# 4. Concurrency & Performance Stress Test
print("\n--- [4] Concurrency & Latency Stress Test (100 parallel requests) ---")
test_urls = [
    f"{BASE_URL}/api/v1/system/status",
    f"{BASE_URL}/api/v1/market/tickers",
    f"{BASE_URL}/api/v1/risk/rules",
    f"{BASE_URL}/dashboard",
    f"{BASE_URL}/assets/index-oAgbEC-V.js"
]

def fetch_worker(idx):
    target = test_urls[idx % len(test_urls)]
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(target)
        with urllib.request.urlopen(req, timeout=5) as resp:
            t1 = time.perf_counter()
            return {"status": resp.status, "duration_ms": (t1 - t0) * 1000, "error": None}
    except Exception as e:
        t1 = time.perf_counter()
        return {"status": getattr(e, "code", 0), "duration_ms": (t1 - t0) * 1000, "error": str(e)}

start_stress = time.perf_counter()
with ThreadPoolExecutor(max_workers=20) as executor:
    results = list(executor.map(fetch_worker, range(100)))
total_stress_time = time.perf_counter() - start_stress

durations = [r["duration_ms"] for r in results]
durations.sort()
success_count = sum(1 for r in results if r["status"] == 200)
error_count = 100 - success_count
p50 = durations[50]
p95 = durations[95]
p99 = durations[99]

audit_results["concurrency"] = {
    "total_requests": 100,
    "concurrency_workers": 20,
    "success_count": success_count,
    "error_count": error_count,
    "total_duration_sec": round(total_stress_time, 3),
    "p50_ms": round(p50, 2),
    "p95_ms": round(p95, 2),
    "p99_ms": round(p99, 2)
}

print(f"  Total: 100 requests across 20 workers | Total Time: {total_stress_time:.2f}s")
print(f"  Success: {success_count}/100 ({(success_count):.1f}%) | Errors: {error_count}")
print(f"  Latency: p50={p50:.2f}ms | p95={p95:.2f}ms | p99={p99:.2f}ms")

# Summary & Verdict
total_checks = len(audit_results["spa_routes"]) + len(audit_results["static_assets"]) + len(audit_results["api_proxy"])
failed_checks = len(audit_results["failures"])
all_ok = (failed_checks == 0) and (error_count == 0)

audit_results["verdict"] = "APPROVE" if all_ok else "REJECT"

print("\n" + "=" * 80)
print(f"  DEEP AUDIT SUMMARY: Total Checks={total_checks} | Failures={failed_checks}")
print(f"  FINAL VERDICT: >>> {audit_results['verdict']} <<<")
print("=" * 80)

with open("/root/abc-project/challenger_e2e_audit_results.json", "w", encoding="utf-8") as f:
    json.dump(audit_results, f, indent=2)

if not all_ok:
    sys.exit(1)
