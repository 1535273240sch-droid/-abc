import urllib.request
import json
import sys

endpoints = [
    '/health',
    '/api/v1/system/status',
    '/api/v1/market/tickers',
    '/api/v1/market/orderbook/BTCUSDT',
    '/api/v1/market/trades/BTCUSDT',
    '/api/v1/market/funding',
    '/api/v1/market/quality',
    '/api/v1/orders',
    '/api/v1/positions',
    '/api/v1/execution/reconciliation',
    '/api/v1/strategies',
    '/api/v1/research/backtests',
    '/api/v1/risk/rules',
    '/api/v1/risk/circuit-breakers',
    '/api/v1/governance/kill-switch',
    '/api/v1/governance/approvals',
    '/api/v1/agents/tasks',
    '/api/v1/control/exchanges',
    '/api/v1/control/model-providers',
    '/api/v1/live/credentials',
    '/api/v1/audit/events'
]

pages = [
    '/',
    '/dashboard',
    '/market',
    '/execution',
    '/research',
    '/risk',
    '/agents',
    '/settings'
]

print("=== Testing All Frontend Pages (Nginx 80) ===")
all_pages_ok = True
for page in pages:
    url = f"http://127.0.0.1{page}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            print(f"[PAGE 200 OK] {url} (Length: {len(resp.read())} bytes)")
    except Exception as e:
        print(f"[PAGE FAIL] {url}: {e}")
        all_pages_ok = False

print("\n=== Testing All Backend REST Endpoints (Nginx 80 -> Backend 8000) ===")
all_endpoints_ok = True
for ep in endpoints:
    url = f"http://127.0.0.1{ep}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
            json_obj = json.loads(data)
            count = len(json_obj) if isinstance(json_obj, list) else len(json_obj.keys())
            print(f"[API 200 OK] {ep:<38} items/keys: {count}")
    except Exception as e:
        print(f"[API FAIL] {ep}: {e}")
        all_endpoints_ok = False

if all_pages_ok and all_endpoints_ok:
    print("\n>>> ALL CHECKS PASSED: 100% SUCCESS <<<")
    sys.exit(0)
else:
    print("\n>>> CHECKS FAILED <<<")
    sys.exit(1)
