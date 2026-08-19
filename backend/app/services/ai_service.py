import json
import time
import urllib.error
import urllib.request
from typing import Any

from app.core.errors import QuantError
from app.core.network import validate_safe_outbound_url
from app.core.secrets import secret_resolver


class AIService:
    def __init__(self, store: Any):
        self._store = store

    def chat(self, provider_id: str, messages: list[dict], temperature: float, max_tokens: int) -> dict:
        provider = self._store.control_service.get_model_provider(provider_id)
        if not provider:
            raise QuantError("NOT_FOUND", f"Model provider {provider_id} not found", status_code=404)
        if not provider.get("enabled"):
            raise QuantError("MODEL_PROVIDER_DISABLED", f"Model provider {provider_id} is disabled", status_code=409)
        secret = secret_resolver.resolve(provider.get("secret_ref"))
        if not secret:
            raise QuantError("SECRET_NOT_CONFIGURED", "The configured Secret Manager reference cannot be resolved by this runtime", status_code=503)
        if provider.get("model") == "not-configured":
            raise QuantError("MODEL_NOT_CONFIGURED", "A model name is required", status_code=400)

        # Defense in depth: re-validate the outbound destination immediately
        # before the request so an internal/metadata target can never be reached.
        base_url = validate_safe_outbound_url(provider["base_url"])
        url = base_url.rstrip("/") + "/chat/completions"
        payload = json.dumps({
            "model": provider["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {secret.value}",
                "Content-Type": "application/json",
                "User-Agent": "enterprise-ai-quant/0.1"
            },
            method="POST"
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_msg = f"Model provider returned HTTP {exc.code}"
            try:
                err_data = json.loads(exc.read().decode("utf-8"))
                if isinstance(err_data, dict) and "error" in err_data:
                    err_msg = f"Model provider HTTP {exc.code}: {err_data['error'].get('message', err_data['error'])}"
            except Exception:
                pass
            raise QuantError("MODEL_PROVIDER_ERROR", err_msg, status_code=502)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise QuantError("MODEL_PROVIDER_UNAVAILABLE", f"Model provider unavailable: {exc}", status_code=503)
        except (ValueError, json.JSONDecodeError) as exc:
            raise QuantError("MODEL_PROVIDER_INVALID_RESPONSE", f"Model provider returned invalid JSON: {exc}", status_code=502)

        try:
            msg = body["choices"][0]["message"]
            content = msg.get("content") or ""
            # If content is empty but reasoning is present, use reasoning as content
            if not content.strip():
                content = msg.get("reasoning_content") or msg.get("reasoning") or ""
            if not content.strip():
                content = "模型响应成功但无文本内容输出。"
        except (KeyError, IndexError, TypeError) as exc:
            raise QuantError("MODEL_PROVIDER_INVALID_RESPONSE", f"Model provider response missing chat content: {exc}", status_code=502)

        return {
            "provider_id": provider_id,
            "model": provider["model"],
            "content": str(content),
            "usage": body.get("usage", {}),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "status": "completed"
        }
