import urllib.request
import urllib.error
import json
import time
from app.db.db_store import DBStore
from app.services.credential_service import CredentialService
from app.adapters.live_exchange_adapters import build_live_adapter

store = DBStore()
cs = CredentialService(store=store)
creds = cs.resolve("conn-okx-testnet")

adapter = build_live_adapter("okx", creds, dry_run=False, is_demo=True)
adapter.connect()

print("================================================================")
print("             OKX API Key 深度权限与市场配置探测                ")
print("================================================================")

# 1. 探测账户配置与权限
def test_get(endpoint, name):
    print(f"\n[GET {endpoint}] - {name}:")
    headers = adapter.sign("GET", endpoint)
    req = urllib.request.Request(f"https://www.okx.com{endpoint}", headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return data
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"Error: {e}")

# 探测账户模式 (现货/全仓保证金等)
test_get("/api/v5/account/config", "账户综合配置与交易模式")
# 探测最大可买数量 (检查现货买卖权限)
test_get("/api/v5/account/max-buy-sell-amount?instId=BTC-USDT", "BTC-USDT 现货最大可买可卖额度")
# 探测杠杆/合约额度
test_get("/api/v5/account/max-buy-sell-amount?instId=BTC-USDT-SWAP&tdMode=cross", "BTC-USDT-SWAP 永续合约交易额度")

# 2. 测试不同下单参数组合
def test_post_order(body, label, is_demo=True):
    print(f"\n--- 测试下单: {label} ---")
    headers = adapter.sign("POST", "/api/v5/trade/order", body=body)
    if not is_demo and "x-simulated-trading" in headers:
        del headers["x-simulated-trading"]
    data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request("https://www.okx.com/api/v5/trade/order", data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            print("✓ 成功返回:", json.dumps(res, indent=2, ensure_ascii=False))
    except urllib.error.HTTPError as e:
        print(f"✗ HTTP {e.code}: {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"✗ Error: {e}")

# 测试 A: 现货限价 (cash)
test_post_order({
    "instId": "BTC-USDT",
    "tdMode": "cash",
    "side": "buy",
    "ordType": "limit",
    "sz": "0.0001",
    "px": "20000.00",
    "clOrdId": f"tA{int(time.time()*1000)}"[:32]
}, "A. 现货 BTC-USDT (tdMode=cash)")

# 测试 B: 现货全仓 (cross)
test_post_order({
    "instId": "BTC-USDT",
    "tdMode": "cross",
    "side": "buy",
    "ordType": "limit",
    "sz": "0.0001",
    "px": "20000.00",
    "clOrdId": f"tB{int(time.time()*1000)}"[:32]
}, "B. 现货 BTC-USDT (tdMode=cross)")

# 测试 C: 永续合约 (BTC-USDT-SWAP, cross, net)
test_post_order({
    "instId": "BTC-USDT-SWAP",
    "tdMode": "cross",
    "side": "buy",
    "posSide": "net",
    "ordType": "limit",
    "sz": "1",
    "px": "20000.00",
    "clOrdId": f"tC{int(time.time()*1000)}"[:32]
}, "C. 永续合约 BTC-USDT-SWAP (tdMode=cross, posSide=net)")

# 测试 D: 永续合约 (BTC-USDT-SWAP, cross, long)
test_post_order({
    "instId": "BTC-USDT-SWAP",
    "tdMode": "cross",
    "side": "buy",
    "posSide": "long",
    "ordType": "limit",
    "sz": "1",
    "px": "20000.00",
    "clOrdId": f"tD{int(time.time()*1000)}"[:32]
}, "D. 永续合约 BTC-USDT-SWAP (tdMode=cross, posSide=long)")
