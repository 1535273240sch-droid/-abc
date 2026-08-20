from app.db.db_store import DBStore
from app.services.credential_service import CredentialService
from app.adapters.live_exchange_adapters import build_live_adapter
import urllib.request
import urllib.error

store = DBStore()
cs = CredentialService(store=store)
creds = cs.resolve("conn-okx-testnet")
adapter = build_live_adapter("okx", creds, dry_run=False, is_demo=True)
adapter.connect()

body = {
    "instId": "BTC-USDT",
    "tdMode": "cash",
    "side": "buy",
    "ordType": "limit",
    "sz": "0.0001",
    "px": "20000.00",
    "clOrdId": "test123456789012"
}

headers = adapter.sign("POST", "/api/v5/trade/order", body=body)
import json
data = json.dumps(body, separators=(",", ":")).encode("utf-8")

req = urllib.request.Request("https://www.okx.com/api/v5/trade/order", data=data, headers=headers, method="POST")

try:
    with urllib.request.urlopen(req) as resp:
        print("Response:", resp.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    print("HTTPError code:", e.code)
    print("HTTPError body:", e.read().decode("utf-8"))
