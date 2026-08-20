from app.db.db_store import DBStore

store = DBStore()

print("--- 1. Exchange Connections Check ---")
print("Exchange connections count:", len(store.exchange_connections))
for k, v in store.exchange_connections.items():
    print(f" - ID: {k}, Data: {v}")

print("\n--- 2. Recent Orders Check ---")
print("Orders count:", len(store.orders))
for oid, ord_obj in list(store.orders.items())[-10:]:
    print(f" - Order ID: {oid}, Symbol: {ord_obj.symbol}, Side: {ord_obj.side}, Mode: {ord_obj.mode}, Status: {ord_obj.status}, Account: {ord_obj.account_id}")

print("\n--- 3. Adapter Service & Connections Check ---")
print("Managed adapters:", store.adapter_service._manager._adapters.keys())
for name, managed in store.adapter_service._manager._adapters.items():
    print(f" - Adapter [{name}]: status={managed.status}, type={type(managed._adapter).__name__}")
