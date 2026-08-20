from app.db.db_store import DBStore
from app.services.credential_service import CredentialService

store = DBStore()
cs = CredentialService(store=store)

print("--- Testing OKX Connection ---")
try:
    res = cs.test("conn-okx-testnet")
    for k, v in res.items():
        print(f" {k}: {v}")
except Exception as e:
    print("Test exception:", type(e), e)
