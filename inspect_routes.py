import sys
import os

sys.path.insert(0, "/root/abc-project/backend")
from app.main import app

print("=== ALL REGISTERED APP.MAIN ROUTES ===")
for r in app.routes:
    methods = getattr(r, "methods", ["ANY"])
    path = getattr(r, "path", str(r))
    name = getattr(r, "name", "")
    print(f"{list(methods)}: {path} ({name})")
