import urllib.request
import json
from app.db.db_store import DBStore
from app.services.credential_service import CredentialService
from app.adapters.live_exchange_adapters import build_live_adapter

store = DBStore()
cs = CredentialService(store=store)
creds = cs.resolve("conn-okx-testnet")
adapter = build_live_adapter("okx", creds, dry_run=False, is_demo=True)
adapter.connect()

print("--- 正在向 OKX 官方服务器拉取当前模拟盘真实委托列表 (GET /api/v5/trade/orders-pending) ---")
headers = adapter.sign("GET", "/api/v5/trade/orders-pending")
req = urllib.request.Request("https://www.okx.com/api/v5/trade/orders-pending", headers=headers, method="GET")

with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    orders = data.get("data", [])
    print(f"OKX 模拟盘当前挂单总数: {len(orders)} 笔")
    for o in orders:
        print(f" • 订单ID [ordId]: {o.get('ordId')}")
        print(f"   交易品种 [instId]: {o.get('instId')}")
        print(f"   买卖方向 [side]: {o.get('side')} (持仓方向: {o.get('posSide')})")
        print(f"   委托价格 [px]: ${o.get('px')}")
        print(f"   委托数量 [sz]: {o.get('sz')}")
        print(f"   当前状态 [state]: {o.get('state')}")
        print(f"   创建时间 [cTime]: {o.get('cTime')}")
        print("-" * 50)
