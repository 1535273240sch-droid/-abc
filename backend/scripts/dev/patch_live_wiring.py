with open("/root/abc-project/backend/app/services/credential_service.py", "r", encoding="utf-8") as f:
    content = f.read()

old_dry_run = "dry_run=not settings.live_trading_enabled,"
new_dry_run = "dry_run=not settings.live_trading_enabled and not is_demo,"
if old_dry_run in content:
    content = content.replace(old_dry_run, new_dry_run)
    with open("/root/abc-project/backend/app/services/credential_service.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ credential_service.py patched: dry_run=False for is_demo")
else:
    print("credential_service.py already patched")

# Patch connection_manager.py
with open("/root/abc-project/backend/app/adapters/connection_manager.py", "r", encoding="utf-8") as f:
    cm_content = f.read()

old_cm_connect = """    def connect(self) -> AdapterHealth:
        with self._lock:
            self._status = AdapterConnectionStatus.CONNECTING
            self._last_error = None
            # Simulate connection latency
            self._latency_ms = 42 if self.name in ("binance",) else 58
            self._status = AdapterConnectionStatus.CONNECTED
            return self._build_health()"""

new_cm_connect = """    def connect(self) -> AdapterHealth:
        with self._lock:
            self._status = AdapterConnectionStatus.CONNECTING
            self._last_error = None
            if hasattr(self._adapter, "connect"):
                try:
                    self._adapter.connect()
                except Exception as e:
                    self._status = AdapterConnectionStatus.FAILED
                    self._last_error = str(e)
                    raise
            self._latency_ms = 42 if self.name in ("binance",) else 58
            self._status = AdapterConnectionStatus.CONNECTED
            return self._build_health()"""

if old_cm_connect in cm_content:
    cm_content = cm_content.replace(old_cm_connect, new_cm_connect)
    with open("/root/abc-project/backend/app/adapters/connection_manager.py", "w", encoding="utf-8") as f:
        f.write(cm_content)
    print("✓ connection_manager.py patched: inner adapter connected")
else:
    print("connection_manager.py already patched")
