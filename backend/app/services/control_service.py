from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.errors import QuantError
from app.core.network import validate_safe_outbound_url
from app.core.secrets import secret_resolver


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ControlService:
    """Configuration registry that stores references, never credential values."""

    def __init__(self, store: Any):
        self._store = store
        self._seed_model_providers()
        self._seed_exchange_connections()

    def _seed_model_providers(self) -> None:
        defaults = [
            ("deepseek", "DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat", ["chat", "reasoning"]),
            ("openai", "OpenAI", "https://api.openai.com/v1", "gpt-4o", ["chat", "embeddings"]),
            ("anthropic", "Anthropic Claude", "https://api.anthropic.com/v1", "claude-3-5-sonnet-20241022", ["chat"]),
            ("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta", "gemini-1.5-pro", ["chat", "embeddings"]),
            ("stepfun", "StepFun", "https://api.stepfun.com/v1", "step-2-16k", ["chat", "reasoning"]),
        ]
        for provider_id, display_name, base_url, model, capabilities in defaults:
            self._store.model_providers.setdefault(provider_id, {
                "provider_id": provider_id,
                "display_name": display_name,
                "base_url": base_url,
                "model": model,
                "secret_ref": None,
                "enabled": False,
                "capabilities": capabilities,
                "status": "not_configured",
                "runtime_ready": False,
                "updated_at": _now(),
                "last_test_at": None,
                "last_error": None,
            })

    def _seed_exchange_connections(self) -> None:
        for adapter_name in ("binance", "okx", "bybit", "paper"):
            connection_id = f"{adapter_name}-paper"
            self._store.exchange_connections.setdefault(connection_id, {
                "connection_id": connection_id,
                "adapter_name": adapter_name,
                "display_name": f"{adapter_name.upper()} Paper Adapter",
                "environment": "paper",
                "secret_ref": None,
                "enabled": adapter_name == "paper",
                "updated_at": _now(),
            })
        exchanges = [
            ("binance", "Binance", "live"),
            ("okx", "OKX", "live"),
            ("coinbase", "Coinbase", "live"),
        ]
        for adapter_name, display_name, env in exchanges:
            connection_id = adapter_name
            self._store.exchange_connections.setdefault(connection_id, {
                "connection_id": connection_id,
                "adapter_name": adapter_name,
                "display_name": display_name,
                "environment": env,
                "secret_ref": None,
                "enabled": False,
                "adapter_status": "disconnected",
                "credential_status": "not_configured",
                "latency_ms": None,
                "last_error": None,
                "updated_at": _now(),
            })

    def list_model_providers(self) -> list[dict]:
        return sorted(self._store.model_providers.values(), key=lambda item: item["provider_id"])

    def get_model_provider(self, provider_id: str) -> dict | None:
        return self._store.model_providers.get(provider_id)

    def upsert_model_provider(self, payload: dict) -> dict:
        _validate_base_url(payload["base_url"])
        existing = self._store.model_providers.get(payload["provider_id"], {})
        availability = secret_resolver.availability(payload.get("secret_ref"))
        item = {**existing, **payload, "status": "secret_resolved" if availability == "resolved" else "configured_reference" if payload.get("secret_ref") else "not_configured", "runtime_ready": availability == "resolved", "updated_at": _now(), "last_error": None}
        self._store.model_providers[payload["provider_id"]] = item
        return item

    def test_model_provider(self, provider_id: str) -> dict:
        provider = self._store.model_providers.get(provider_id)
        if not provider:
            raise QuantError("NOT_FOUND", f"Model provider {provider_id} not found", status_code=404)
        tested_at = _now()
        if not provider.get("enabled"):
            status, message, ready = "disabled", "Provider is disabled", False
        elif not provider.get("secret_ref"):
            status, message, ready = "not_configured", "No Secret Manager reference configured", False
        elif secret_resolver.resolve(provider.get("secret_ref")):
            status, message, ready = "secret_resolved", "Secret reference resolved by the environment provider", True
        else:
            status, message, ready = "reference_configured", "Secret reference is present; runtime secret resolver is required", False
        provider.update({"status": status, "runtime_ready": ready, "last_test_at": tested_at, "last_error": None if status != "not_configured" else message})
        return {"provider_id": provider_id, "status": status, "runtime_ready": ready, "message": message, "tested_at": tested_at}

    def list_exchange_connections(self) -> list[dict]:
        adapters = {item["name"]: item for item in self._store.adapter_service.list_adapters()}
        result = []
        for config in self._store.exchange_connections.values():
            adapter_name = config.get("adapter_name") or config.get("exchange") or (config.get("connection_id", "").split("-")[0] if "-" in config.get("connection_id", "") else "paper") or "paper"
            health = adapters.get(adapter_name, {})
            up_at = config.get("updated_at")
            if isinstance(up_at, str):
                try:
                    up_at = datetime.fromisoformat(up_at.replace("Z", "+00:00"))
                except Exception:
                    up_at = _now()
            elif not isinstance(up_at, datetime):
                up_at = _now()

            item = {
                "connection_id": config.get("connection_id", ""),
                "adapter_name": adapter_name,
                "display_name": config.get("display_name") or (adapter_name.capitalize() if adapter_name else "Exchange"),
                "environment": config.get("environment") if config.get("environment") in ("paper", "testnet", "live") else "paper",
                "secret_ref": config.get("secret_ref"),
                "enabled": bool(config.get("enabled", True)),
                "adapter_status": health.get("status", "unknown"),
                "credential_status": "reference_configured" if config.get("secret_ref") else "not_configured",
                "latency_ms": health.get("latency_ms"),
                "last_error": health.get("last_error"),
                "updated_at": up_at,
            }
            result.append(item)
        return sorted(result, key=lambda item: item["connection_id"])

    def upsert_exchange_connection(self, payload: dict) -> dict:
        environment = payload.get("environment", "paper")
        if environment in ("live", "testnet"):
            if not settings.live_trading_enabled:
                raise QuantError(
                    "LIVE_TRADING_NOT_ALLOWED",
                    "Live/testnet exchange connections require QUANT_LIVE_TRADING_ENABLED=true",
                    status_code=403,
                )
        if not self._store.adapter_service.get_adapter(payload["adapter_name"]):
            raise QuantError("NOT_FOUND", f"Adapter {payload['adapter_name']} not found", status_code=404)
        existing = self._store.exchange_connections.get(payload["connection_id"], {})
        item = {**existing, **payload, "updated_at": _now()}
        self._store.exchange_connections[payload["connection_id"]] = item
        return next(item for item in self.list_exchange_connections() if item["connection_id"] == payload["connection_id"])

    def test_exchange_connection(self, connection_id: str) -> dict:
        connection = self._store.exchange_connections.get(connection_id)
        if not connection:
            raise QuantError("NOT_FOUND", f"Exchange connection {connection_id} not found", status_code=404)

        tested_at = _now()
        if not connection.get("enabled"):
            status, message, ready = "disabled", "Exchange connection is disabled", False
        elif connection.get("environment") == "paper":
            status, message, ready = "paper_ready", "Paper adapter is available; no external credentials are used", True
        elif settings.mode == "paper":
            status, message, ready = "blocked_by_mode", "Testnet and live exchange connections are disabled in Paper mode", False
        elif not connection.get("secret_ref"):
            status, message, ready = "not_configured", "No Secret Manager reference configured", False
        elif not secret_resolver.resolve(connection.get("secret_ref")):
            status, message, ready = "reference_configured", "Secret reference is present but not resolved by the runtime provider", False
        else:
            status, message, ready = "credential_resolved", "Credentials resolved; external connectivity still requires adapter network probing", True

        return {"connection_id": connection_id, "status": status, "runtime_ready": ready, "message": message, "tested_at": tested_at}


def _validate_base_url(value: str) -> None:
    # SSRF guard: require HTTPS and reject loopback/private/link-local/metadata
    # hosts so a configured provider URL can never be pointed at internal
    # services or used to exfiltrate the resolved secret.
    validate_safe_outbound_url(value)
