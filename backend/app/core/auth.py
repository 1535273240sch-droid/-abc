import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import settings


ROLE_PERMISSIONS = {
    "viewer": {"GET"},
    "quant": {"GET", "POST", "PATCH"},
    "risk_officer": {"GET", "POST"},
    "admin": {"GET", "POST", "PATCH", "PUT", "DELETE"},
}


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign(message: str) -> str:
    secret = settings.auth_secret.encode()
    return _encode(hmac.new(secret, message.encode(), hashlib.sha256).digest())


def create_access_token(username: str, role: str) -> tuple[str, int]:
    expires_at = int(time.time()) + settings.auth_token_ttl_seconds
    payload = {"sub": username, "role": role, "exp": expires_at}
    body = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    message = f"q1.{body}"
    return f"{message}.{_sign(message)}", expires_at


def verify_access_token(token: str) -> dict[str, Any] | None:
    try:
        version, body, signature = token.split(".", 2)
        message = f"{version}.{body}"
        if version != "q1" or not hmac.compare_digest(signature, _sign(message)):
            return None
        payload = json.loads(_decode(body))
        if int(payload.get("exp", 0)) <= int(time.time()):
            return None
        if payload.get("role") not in ROLE_PERMISSIONS or not payload.get("sub"):
            return None
        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def authenticate(username: str, password: str) -> str | None:
    if not settings.auth_enabled or not settings.auth_secret or not settings.auth_admin_password:
        return None
    if not hmac.compare_digest(username, settings.auth_admin_username):
        return None
    if not hmac.compare_digest(password, settings.auth_admin_password):
        return None
    token, _ = create_access_token(username, "admin")
    return token


# Sensitive path prefixes and the roles allowed to access them. A hit on any
# prefix restricts access to exactly these roles for every HTTP method,
# including read-only GET requests (this is what prevents a `viewer` from
# reading control-plane / system / audit data).
_SENSITIVE_PATHS: dict[str, set[str]] = {
    "/api/v1/governance": {"admin", "risk_officer"},
    "/api/v1/control": {"admin"},
    "/api/v1/system": {"admin", "risk_officer", "quant"},
    "/api/v1/adapters": {"admin", "risk_officer", "quant"},
    "/api/v1/audit": {"admin", "risk_officer", "quant"},
    "/api/v1/agents": {"admin", "quant"},
    "/api/v1/ai": {"admin", "quant"},
}


def _role_allows_path(role: str, path: str) -> bool:
    """Return the role gate for a sensitive path, or None if not sensitive."""
    for prefix, allowed in _SENSITIVE_PATHS.items():
        if path.startswith(prefix):
            return role in allowed
    return None


def role_allows(role: str, method: str, path: str) -> bool:
    if role not in ROLE_PERMISSIONS:
        return False
    gate = _role_allows_path(role, path)
    if gate is not None:
        return gate
    if method == "GET":
        # Non-sensitive read access is open to every role with GET permission.
        return "GET" in ROLE_PERMISSIONS[role]
    if method in ROLE_PERMISSIONS[role]:
        return True
    # Fallback for write methods on resource prefixes not listed above.
    if path.startswith("/api/v1/risk"):
        return role in {"admin", "risk_officer", "quant"}
    if path.startswith("/api/v1/orders") or path.startswith("/api/v1/execution"):
        return role in {"admin", "quant"}
    if path.startswith("/api/v1/portfolio") or path.startswith("/api/v1/research"):
        return role in {"admin", "quant"}
    if path.startswith("/api/v1/strategies"):
        return role in {"admin", "quant"}
    return role == "admin"
