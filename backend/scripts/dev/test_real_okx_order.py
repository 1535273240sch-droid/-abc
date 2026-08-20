from app.db.db_store import DBStore
from app.services.credential_service import CredentialService
from app.adapters.live_exchange_adapters import build_live_adapter
from app.adapters.connection_manager import ManagedAdapter
from app.adapters.protocol import AdapterConnectionStatus
import uuid

store = DBStore()
cs = CredentialService(store=store)

# Resolve OKX Testnet credentials
creds = cs.resolve("conn-okx-testnet")
print("OKX Testnet Credentials found for key ending with:", creds.get("api_key", "")[-6:])

# Build live adapter with dry_run=False, is_demo=True
okx_adapter = build_live_adapter("okx", creds, dry_run=False, is_demo=True)
okx_adapter.connect()
print("Connected to OKX. Status:", okx_adapter._status)

managed = ManagedAdapter("okx-testnet", okx_adapter)
managed._status = AdapterConnectionStatus.CONNECTED

print("\n--- 1. Placing Real Order to OKX Simulated Trading ---")
cl_ord_id = f"test{uuid.uuid4().hex[:16]}"
try:
    # Placing Limit BUY 0.0001 BTC @ $20,000 (Safe far below market on demo account)
    res = managed.place_order(
        client_order_id=cl_ord_id,
        symbol="BTC-USDT",
        side="buy",
        quantity="0.0001",
        price="20000.00"
    )
    print("✓ OKX API Response on Place Order:")
    print(" - Exchange:", res.exchange)
    print(" - Status:", res.status)
    print(" - Details:", res.text)
    
    print("\n--- 2. Cancelling Order on OKX ---")
    c_res = managed.cancel_order(client_order_id=cl_ord_id, symbol="BTC-USDT")
    print("✓ OKX API Response on Cancel Order:")
    print(" - Exchange:", c_res.exchange)
    print(" - Status:", c_res.status)
    print(" - Details:", c_res.text)
except Exception as e:
    print("Order error:", type(e), e)
