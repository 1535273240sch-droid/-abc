"""Exchange credential management: encrypted at rest, never in API output.

Storage model (store.exchange_connections entries with environment=live/testnet):
    - ``credential_token``: seal_dict-encrypted api_key/api_secret/passphrase
    - OR ``secret_ref``: env:// reference resolved at runtime (legacy path)

The service never returns decrypted values; ``redacted`` view masks keys.
On save/remove it refreshes live adapters registered in AdapterService so
the execution path can route orders to the real exchange immediately.
"""

import os
from datetime import datetime, timezone
from typing import Any

from app.adapters.adapter_service import AdapterService
from app.adapters.live_exchange_adapters import build_live_adapter
from app.adapters.protocol import AdapterError, ExchangeAdapter
from app.core.config import settings
from app.core.credential_crypto import CredentialCryptoError, open_dict, seal_dict
from app.core.errors import QuantError
from app.core.logging import get_logger
from app.core.network import validate_safe_outbound_url
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc

logger = get_logger(__name__)

SUPPORTED_EXCHANGES = ("binance", "okx", "coinbase")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CredentialService:
    def __init__(self, store: Any):
        self._store = store

    # ── master key ───────────────────────────────────────────────────

    @staticmethod
    def _master_key() -> bytes:
        key = settings.secrets_master_key or settings.auth_secret
        if not key or len(key) < 16:
            raise QuantError(
                "SECRETS_NOT_CONFIGURED",
                "QUANT_SECRETS_MASTER_KEY (or QUANT_AUTH_SECRET) must be set to at least 16 characters "
                "before storing exchange credentials",
                status_code=409,
            )
        return key.encode("utf-8")

    # ── CRUD ─────────────────────────────────────────────────────────

    def save(
        self,
        connection_id: str,
        exchange: str,
        api_key: str,
        api_secret: str,
        passphrase: str | None = None,
        environment: str = "live",
        base_url: str | None = None,
        requested_by: str = "admin",
    ) -> dict:
        exchange = exchange.lower().strip()
        if exchange not in SUPPORTED_EXCHANGES:
            raise QuantError(
                "VALIDATION_ERROR",
                f"Unsupported exchange {exchange!r}, supported: {list(SUPPORTED_EXCHANGES)}",
                status_code=400,
            )
        if environment not in ("live", "testnet"):
            raise QuantError("VALIDATION_ERROR", "environment must be 'live' or 'testnet'", status_code=400)
        if not api_key.strip() or not api_secret.strip():
            raise QuantError("VALIDATION_ERROR", "api_key and api_secret must be non-empty", status_code=400)
        if exchange == "okx" and not (passphrase or "").strip():
            raise QuantError("VALIDATION_ERROR", "okx requires a passphrase", status_code=400)
        if base_url:
            validate_safe_outbound_url(base_url)

        # credential_token holds the sealed secret only; the live trading
        # authorization (config flag + approval) gates actual use.
        payload = {"api_key": api_key.strip(), "api_secret": api_secret.strip()}
        if passphrase:
            payload["passphrase"] = passphrase.strip()
        token = seal_dict(self._master_key(), payload)

        existing = self._store.exchange_connections.get(connection_id, {})
        record = {
            **existing,
            "connection_id": connection_id,
            "adapter_name": exchange,
            "display_name": f"{exchange.upper()} {environment.capitalize()}",
            "environment": environment,
            "base_url": base_url,
            "secret_ref": None,
            "credential_token": token,
            "credential_fingerprint": _fingerprint(api_key),
            "has_passphrase": bool(passphrase and passphrase.strip()),
            "enabled": True,
            "updated_at": _now(),
            "updated_by": requested_by,
        }
        self._store.exchange_connections[connection_id] = record
        if hasattr(self._store, "save"):
            self._store.save()
        self.refresh_live_adapters()

        event_bus.publish(DomainEvent(
            event_type=event_type("credentials", "saved"),
            event_id=new_event_id("cred"),
            event_time=now_utc(),
            version=1,
            actor=requested_by,
            resource_type="exchange_connection",
            resource_id=connection_id,
            payload={"exchange": exchange, "environment": environment, "fingerprint": record["credential_fingerprint"]},
        ))
        logger.info("credential_saved", connection_id=connection_id, exchange=exchange, environment=environment)
        return self.redacted(connection_id)

    def delete(self, connection_id: str, operator: str = "admin") -> dict:
        record = self._store.exchange_connections.get(connection_id)
        if not record:
            raise QuantError("NOT_FOUND", f"Exchange connection {connection_id} not found", status_code=404)
        if record.get("environment") == "paper":
            raise QuantError("VALIDATION_ERROR", "Paper connections are managed by the system", status_code=400)
        del self._store.exchange_connections[connection_id]
        if hasattr(self._store, "save"):
            self._store.save()
        self.refresh_live_adapters()
        event_bus.publish(DomainEvent(
            event_type=event_type("credentials", "deleted"),
            event_id=new_event_id("cred"),
            event_time=now_utc(),
            version=1,
            actor=operator,
            resource_type="exchange_connection",
            resource_id=connection_id,
            payload={"exchange": record.get("adapter_name")},
        ))
        return {"deleted": connection_id}

    def list_credentials(self) -> list[dict]:
        out = []
        for record in self._store.exchange_connections.values():
            if record.get("environment") in ("live", "testnet"):
                out.append(self._redacted_record(record))
        return sorted(out, key=lambda r: r["connection_id"])

    def get_record(self, connection_id: str) -> dict | None:
        record = self._store.exchange_connections.get(connection_id)
        if not record or record.get("environment") not in ("live", "testnet"):
            return None
        return record

    def redacted(self, connection_id: str) -> dict:
        record = self.get_record(connection_id)
        if not record:
            raise QuantError("NOT_FOUND", f"Exchange connection {connection_id} not found", status_code=404)
        return self._redacted_record(record)

    @staticmethod
    def _redacted_record(record: dict) -> dict:
        return {
            "connection_id": record["connection_id"],
            "exchange": record["adapter_name"],
            "environment": record.get("environment"),
            "base_url": record.get("base_url"),
            "enabled": record.get("enabled", False),
            "credential_status": "stored_encrypted" if record.get("credential_token") else (
                "env_reference" if record.get("secret_ref") else "not_configured"
            ),
            "credential_fingerprint": record.get("credential_fingerprint"),
            "has_passphrase": bool(record.get("has_passphrase")),
            "updated_at": record.get("updated_at"),
        }

    # ── resolution ───────────────────────────────────────────────────

    def resolve(self, connection_id: str) -> dict[str, str]:
        """Decrypt credentials for internal use. Never exposed via API."""
        record = self.get_record(connection_id)
        if not record:
            raise QuantError("NOT_FOUND", f"Exchange connection {connection_id} not found", status_code=404)
        token = record.get("credential_token")
        if token:
            try:
                return open_dict(self._master_key(), token)
            except CredentialCryptoError as exc:
                raise QuantError(
                    "CREDENTIAL_DECRYPT_FAILED",
                    f"Cannot decrypt credentials for {connection_id}: {exc}",
                    status_code=500,
                ) from exc
        ref = record.get("secret_ref")
        if ref and ref.startswith("env://"):
            value = os.getenv(ref.removeprefix("env://"), "")
            if value:
                parts = dict(item.split("=", 1) for item in value.split(";") if "=" in item)
                if "api_key" in parts and "api_secret" in parts:
                    return parts
        raise QuantError(
            "CREDENTIALS_NOT_CONFIGURED",
            f"No usable credentials configured for {connection_id}",
            status_code=409,
        )

    def test(self, connection_id: str) -> dict:
        """Connectivity + credential probe (balance query, no orders)."""
        record = self.get_record(connection_id)
        if not record:
            raise QuantError("NOT_FOUND", f"Exchange connection {connection_id} not found", status_code=404)
        try:
            creds = self.resolve(connection_id)
        except QuantError as exc:
            record["last_error"] = exc.message
            return {"connection_id": connection_id, "status": "not_configured", "message": exc.message, "tested_at": _now()}
        is_demo = record.get("environment") == "testnet" or "testnet" in str(record.get("connection_id", "")).lower()
        adapter = build_live_adapter(
            record["adapter_name"],
            creds,
            base_url=record.get("base_url"),
            dry_run=True,
            is_demo=is_demo,
        )
        try:
            adapter.connect()
            balance = adapter.get_balance()
            status, message = "connected", f"credentials valid, balance probe ok ({balance})"
            record["last_error"] = None
        except AdapterError as exc:
            status, message = "failed", exc.message
            record["last_error"] = exc.message
        record["last_test_at"] = _now()
        return {"connection_id": connection_id, "status": status, "message": message, "tested_at": record["last_test_at"]}

    # ── adapter wiring ───────────────────────────────────────────────

    def refresh_live_adapters(self) -> list[str]:
        """(Re)register live adapters for every usable credential record.

        Replaces the seeded paper adapters for exchanges that have real
        credentials, so the execution service transparently gains a live
        path. Registered under name ``<exchange>-live``.
        """
        wired: list[str] = []
        adapter_service: AdapterService = self._store.adapter_service
        for record in self._store.exchange_connections.values():
            if record.get("environment") not in ("live", "testnet") or not record.get("enabled"):
                continue
            try:
                creds = self.resolve(record["connection_id"])
                is_demo = record.get("environment") == "testnet"
                adapter = build_live_adapter(
                    record["adapter_name"], creds,
                    base_url=record.get("base_url"),
                    dry_run=not settings.live_trading_enabled and not is_demo,
                    is_demo=is_demo,
                )
            except (QuantError, AdapterError) as exc:
                logger.warning("live_adapter_wire_failed", connection_id=record["connection_id"], error=str(exc)[:200])
                continue
            name = f"{record['adapter_name']}-live"
            existing = adapter_service._manager.get(name)
            if existing is not None:
                adapter_service._manager._adapters.pop(name, None)
            adapter_service._manager.register(name, adapter, max_rps=8.0, max_retries=2)
            wired.append(name)
        return wired

    def live_adapter(self, exchange: str) -> ExchangeAdapter | None:
        return self._store.adapter_service._manager.get(f"{exchange.lower()}-live")


def _fingerprint(api_key: str) -> str:
    import hashlib

    digest = hashlib.sha256(api_key.encode()).hexdigest()
    return f"{api_key[:3]}…{api_key[-2:]} ({digest[:8]})" if len(api_key) > 6 else "(short)"
