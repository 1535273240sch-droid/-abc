"""RFC 7519 compliant JWT Authentication and RBAC Security module."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from datetime import timedelta
from typing import Any, Callable

from fastapi import Depends, Header, Request

from app.core.api_key import extract_bearer_token
from app.core.config import settings
from app.core.errors import QuantError


# ── Standard Role Definitions & Permission Matrix (OWASP RBAC) ──────────────

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "viewer": {"GET"},
    "auditor": {"GET"},
    "quant": {"GET", "POST", "PATCH", "DELETE"},
    "trader": {"GET", "POST", "PATCH", "DELETE"},
    "risk_officer": {"GET", "POST", "PATCH", "PUT", "DELETE"},
    "risk_admin": {"GET", "POST", "PATCH", "PUT", "DELETE"},
    "admin": {"GET", "POST", "PATCH", "PUT", "DELETE"},
}

ROLE_ALIASES: dict[str, str] = {
    "quant": "trader",
    "risk_officer": "risk_admin",
    "viewer": "auditor",
}

ROLE_PERMISSIONS_MAP: dict[str, set[str]] = {
    "trader": {
        "order:create",
        "order:cancel",
        "strategy:manage",
        "backtest:run",
        "trade:view_own",
    },
    "risk_admin": {
        "order:force_cancel_all",
        "position:liquidate",
        "risk:kill_switch",
        "risk:config_update",
        "live:unlock_gate",
        "strategy:manage",
        "alert:config",
        "trade:view_own",
        "trade:view_all",
        "audit:view_logs",
    },
    "auditor": {
        "trade:view_own",
        "trade:view_all",
        "audit:view_logs",
    },
    "admin": {
        "order:create",
        "order:cancel",
        "order:force_cancel_all",
        "position:liquidate",
        "risk:kill_switch",
        "risk:config_update",
        "live:unlock_gate",
        "strategy:manage",
        "backtest:run",
        "alert:config",
        "trade:view_own",
        "trade:view_all",
        "audit:view_logs",
        "user:manage",
    },
    "quant": {
        "order:create",
        "order:cancel",
        "strategy:manage",
        "backtest:run",
        "trade:view_own",
    },
    "risk_officer": {
        "order:force_cancel_all",
        "position:liquidate",
        "risk:kill_switch",
        "risk:config_update",
        "live:unlock_gate",
        "strategy:manage",
        "alert:config",
        "trade:view_own",
        "trade:view_all",
        "audit:view_logs",
    },
    "viewer": {
        "trade:view_own",
        "trade:view_all",
        "audit:view_logs",
    },
}


def get_permissions_for_role(role: str) -> set[str]:
    """Return all fine-grained permission keys granted to a given role."""
    r = role.lower()
    if r in ROLE_PERMISSIONS_MAP:
        return set(ROLE_PERMISSIONS_MAP[r])
    if r in ROLE_ALIASES:
        target = ROLE_ALIASES[r]
        return set(ROLE_PERMISSIONS_MAP.get(target, set()))
    return set()


# ── Password Hashing & Verification (PBKDF2-SHA256) ─────────────────────────

def hash_password(password: str) -> str:
    """Generate a secure PBKDF2-SHA256 salted hash of the plaintext password."""
    salt = secrets.token_hex(16)
    iterations = 100_000
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password in constant time against PBKDF2-SHA256 or plaintext admin config."""
    if not plain_password or not hashed_password:
        return False
    try:
        if hashed_password.startswith("pbkdf2_sha256$"):
            parts = hashed_password.split("$")
            if len(parts) != 4:
                return False
            iterations = int(parts[1])
            salt = parts[2]
            expected_hex = parts[3]
            key = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode("utf-8"),
                salt.encode("utf-8"),
                iterations,
            )
            return hmac.compare_digest(key.hex(), expected_hex)
        # Fallback for plain config or legacy match
        return hmac.compare_digest(plain_password, hashed_password)
    except Exception:
        return False


# ── Thread-Safe In-Memory User Store ────────────────────────────────────────

_USER_DB: dict[str, dict[str, Any]] = {}
_USER_LOCK = threading.Lock()


def get_user(username: str) -> dict[str, Any] | None:
    """Retrieve user record by username."""
    with _USER_LOCK:
        user = _USER_DB.get(username)
        return dict(user) if user else None


def create_user(
    username: str,
    password: str,
    role: str = "trader",
    permissions: list[str] | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    """Register and store a new user record."""
    role_norm = role.lower()
    granted_perms = list(permissions) if permissions is not None else list(get_permissions_for_role(role_norm))
    user_id = f"usr_{secrets.token_hex(6)}"
    now = int(time.time())

    user_data = {
        "user_id": user_id,
        "username": username,
        "password_hash": hash_password(password),
        "role": role_norm,
        "roles": [role_norm],
        "permissions": granted_perms,
        "is_active": True,
        "created_at": now,
        "email": email,
    }

    with _USER_LOCK:
        _USER_DB[username] = user_data
    return dict(user_data)


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    """Authenticate username & password against in-memory user registry."""
    with _USER_LOCK:
        user = _USER_DB.get(username)
        if not user:
            return None
        if not user.get("is_active", True):
            return None
        if not verify_password(password, user["password_hash"]):
            return None
        return dict(user)


def reset_users() -> None:
    """Clear in-memory user store (used in testing)."""
    with _USER_LOCK:
        _USER_DB.clear()


# ── Base64URL & Crypto Helpers ──────────────────────────────────────────────

def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _get_secret() -> bytes:
    raw = settings.auth_secret or "e105ba4a836ff066bef78b31655019ce96b4e8a9a233cd4097fdbc75fc35e786"
    return raw.encode("utf-8")


def _sign(message: str) -> str:
    secret = _get_secret()
    return _encode(hmac.new(secret, message.encode("utf-8"), hashlib.sha256).digest())


# ── Token Result Type (compatible with str and tuple unpacking) ──────────────

class TokenResult(str):
    """String subclass that also supports unpacking as (token, expires_at)."""

    def __new__(cls, token: str, expires_at: int):
        obj = super().__new__(cls, token)
        obj.expires_at = expires_at
        return obj

    def __iter__(self):
        yield str(self)
        yield self.expires_at


# ── Standard RFC 7519 JWT HS256 Token Issuance & Verification ───────────────

JWT_HEADER = {"alg": "HS256", "typ": "JWT"}
JWT_ISSUER = "enterprise-quant-system"


def create_access_token(
    data_or_username: dict[str, Any] | str | None = None,
    role: str | None = None,
    expires_delta: timedelta | int | None = None,
    permissions: list[str] | None = None,
    *,
    username: str | None = None,
    data: dict[str, Any] | None = None,
) -> TokenResult:
    """Issue a standard RFC 7519 HS256 JWT access token."""
    now = int(time.time())
    ttl = settings.auth_token_ttl_seconds
    if isinstance(expires_delta, timedelta):
        ttl = int(expires_delta.total_seconds())
    elif isinstance(expires_delta, int):
        ttl = expires_delta

    expires_at = now + ttl

    target_data = data_or_username if data_or_username is not None else (data if data is not None else username)
    if target_data is None:
        target_data = "user"

    if isinstance(target_data, dict):
        payload = target_data.copy()
        sub = str(payload.get("sub") or payload.get("username") or "user")
        user_role = str(role or payload.get("role") or "trader")
        roles = payload.get("roles") or [user_role]
        perms = payload.get("permissions") or permissions or list(get_permissions_for_role(user_role))
        payload.setdefault("sub", sub)
        payload.setdefault("username", sub)
        payload["role"] = user_role
        payload["roles"] = roles
        payload["permissions"] = perms
        payload["iss"] = payload.get("iss", JWT_ISSUER)
        payload["iat"] = payload.get("iat", now)
        payload["exp"] = payload.get("exp", expires_at)
        payload["type"] = "access"
        expires_at = int(payload["exp"])
    else:
        u_name = str(target_data)
        user_role = str(role or "trader")
        granted_perms = permissions if permissions is not None else list(get_permissions_for_role(user_role))
        payload = {
            "sub": u_name,
            "username": u_name,
            "role": user_role,
            "roles": [user_role],
            "permissions": granted_perms,
            "iss": JWT_ISSUER,
            "iat": now,
            "exp": expires_at,
            "type": "access",
        }

    header_b64 = _encode(json.dumps(JWT_HEADER, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    payload_b64 = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    message = f"{header_b64}.{payload_b64}"
    signature = _sign(message)
    token_str = f"{message}.{signature}"

    return TokenResult(token_str, expires_at)


def create_refresh_token(
    data_or_username: dict[str, Any] | str | None = None,
    role: str | None = None,
    expires_delta: timedelta | int | None = None,
    *,
    username: str | None = None,
    data: dict[str, Any] | None = None,
) -> TokenResult:
    """Issue an RFC 7519 HS256 JWT refresh token (default 7 days validity)."""
    now = int(time.time())
    ttl = settings.auth_token_ttl_seconds * 24 * 7  # 7 days
    if isinstance(expires_delta, timedelta):
        ttl = int(expires_delta.total_seconds())
    elif isinstance(expires_delta, int):
        ttl = expires_delta

    expires_at = now + ttl

    target_data = data_or_username if data_or_username is not None else (data if data is not None else username)
    if target_data is None:
        target_data = "user"

    if isinstance(target_data, dict):
        payload = target_data.copy()
        sub = str(payload.get("sub") or payload.get("username") or "user")
        user_role = str(role or payload.get("role") or "trader")
        payload.setdefault("sub", sub)
        payload.setdefault("username", sub)
        payload["role"] = user_role
        payload["iss"] = JWT_ISSUER
        payload["iat"] = now
        payload["exp"] = expires_at
        payload["type"] = "refresh"
    else:
        u_name = str(target_data)
        user_role = str(role or "trader")
        payload = {
            "sub": u_name,
            "username": u_name,
            "role": user_role,
            "iss": JWT_ISSUER,
            "iat": now,
            "exp": expires_at,
            "type": "refresh",
        }

    header_b64 = _encode(json.dumps(JWT_HEADER, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    payload_b64 = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    message = f"{header_b64}.{payload_b64}"
    signature = _sign(message)
    token_str = f"{message}.{signature}"

    return TokenResult(token_str, expires_at)


def verify_token(token: str, token_type: str | None = None) -> dict[str, Any] | None:
    """Verify JWT signature, expiration, and payload structure according to RFC 7519."""
    if not token or not isinstance(token, str):
        return None
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, signature = parts
        message = f"{header_b64}.{payload_b64}"
        expected_sig = _sign(message)
        if not hmac.compare_digest(signature, expected_sig):
            return None

        # Verify header
        try:
            header_data = json.loads(_decode(header_b64))
            if header_data.get("alg") != "HS256":
                return None
        except Exception:
            return None

        payload = json.loads(_decode(payload_b64))
        if not isinstance(payload, dict):
            return None

        # Expiration check
        exp = int(payload.get("exp", 0))
        if exp <= int(time.time()):
            return None

        # Subject check
        if not payload.get("sub"):
            return None

        # Type check (if requested)
        if token_type is not None:
            claimed_type = payload.get("type")
            if claimed_type and claimed_type != token_type:
                return None

        # Ensure role / roles normalization
        role = payload.get("role")
        if role and (role in ROLE_PERMISSIONS or role in ROLE_PERMISSIONS_MAP):
            if "roles" not in payload:
                payload["roles"] = [role]
            if "permissions" not in payload:
                payload["permissions"] = list(get_permissions_for_role(role))

        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def verify_access_token(token: str) -> dict[str, Any] | None:
    """Verify access token (backward compatible alias)."""
    return verify_token(token, token_type=None)


def authenticate(username: str, password: str) -> str | None:
    """Authenticate username and password against system admin config or registered users."""
    if not settings.auth_enabled or not settings.auth_secret:
        return None

    # Check registered users first
    user = authenticate_user(username, password)
    if user:
        token = create_access_token(
            data_or_username=user["username"],
            role=user["role"],
            permissions=user.get("permissions"),
        )
        return str(token)

    # Check configured admin
    if settings.auth_admin_password and hmac.compare_digest(username, settings.auth_admin_username):
        if hmac.compare_digest(password, settings.auth_admin_password) or verify_password(password, settings.auth_admin_password):
            token = create_access_token(username, "admin")
            return str(token)

    return None


# ── Sensitive Path & URL-level RBAC Control ──────────────────────────────────

_SENSITIVE_PATHS: dict[str, set[str]] = {
    "/api/v1/governance": {"admin", "risk_officer", "risk_admin"},
    "/api/v1/control": {"admin"},
    "/api/v1/system": {"admin", "risk_officer", "risk_admin", "quant", "trader"},
    "/api/v1/adapters": {"admin", "risk_officer", "risk_admin", "quant", "trader"},
    "/api/v1/audit": {"admin", "risk_officer", "risk_admin", "quant", "trader", "auditor"},
    "/api/v1/agents": {"admin", "quant", "trader"},
    "/api/v1/ai": {"admin", "quant", "trader"},
}


def _role_allows_path(role: str, path: str) -> bool:
    """Return the role gate for a sensitive path, or None if not sensitive."""
    for prefix, allowed in _SENSITIVE_PATHS.items():
        if path.startswith(prefix):
            return role in allowed
    return None


def role_allows(role: str, method: str, path: str) -> bool:
    """Evaluate whether a given role is allowed to perform method on path."""
    if role not in ROLE_PERMISSIONS:
        return False
    gate = _role_allows_path(role, path)
    if gate is not None:
        if not gate:
            return False
    if method == "GET":
        return "GET" in ROLE_PERMISSIONS[role]
    if method in ROLE_PERMISSIONS[role]:
        if path.startswith("/api/v1/control"):
            return role == "admin"
        if path.startswith("/api/v1/governance"):
            return role in {"admin", "risk_officer", "risk_admin"}
        if path.startswith("/api/v1/orders") or path.startswith("/api/v1/execution"):
            return role in {"admin", "quant", "trader"}
        if path.startswith("/api/v1/risk"):
            return role in {"admin", "risk_officer", "risk_admin", "quant", "trader"}
        if path.startswith("/api/v1/portfolio") or path.startswith("/api/v1/research") or path.startswith("/api/v1/strategies"):
            return role in {"admin", "quant", "trader"}
        if path.startswith("/api/v1/alert"):
            return role in {"admin", "risk_officer", "risk_admin"}
        if path.startswith("/api/v1/audit"):
            return role in {"admin", "risk_officer", "risk_admin"}
        return role == "admin"
    return False


# ── FastAPI Dependencies (RBAC Dependency Injection) ─────────────────────────

async def get_current_user(
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """FastAPI dependency to extract and validate current authenticated user claims."""
    if hasattr(request.state, "user") and request.state.user:
        return request.state.user

    auth_header = authorization or request.headers.get("Authorization")
    if not auth_header:
        raise QuantError("AUTH_REQUIRED", "Authorization header is required", status_code=401)

    scheme, token = extract_bearer_token(auth_header)
    if not token or scheme != "bearer":
        raise QuantError("AUTH_REQUIRED", "A valid Bearer token is required", status_code=401)

    claims = verify_access_token(token)
    if claims is None:
        raise QuantError("AUTH_INVALID_TOKEN", "Token is invalid, expired, or tampered", status_code=401)

    request.state.user = claims
    return claims


def require_role(required_roles: list[str] | str) -> Callable:
    """FastAPI dependency factory enforcing that the authenticated user possesses one of required_roles."""
    if isinstance(required_roles, str):
        required_roles = [required_roles]

    normalized_required = {r.lower() for r in required_roles}
    # Add alias mappings
    for r in list(normalized_required):
        if r in ROLE_ALIASES:
            normalized_required.add(ROLE_ALIASES[r])
        for alias, target in ROLE_ALIASES.items():
            if target == r:
                normalized_required.add(alias)

    async def _role_guard(request: Request, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        user_role = (user.get("role") or "").lower()
        user_roles = {r.lower() for r in user.get("roles", [])}
        if user_role:
            user_roles.add(user_role)

        # Admin superuser always bypasses
        if "admin" in user_roles:
            return user

        # Expand user aliases
        expanded_user_roles = set(user_roles)
        for r in user_roles:
            if r in ROLE_ALIASES:
                expanded_user_roles.add(ROLE_ALIASES[r])
            for alias, target in ROLE_ALIASES.items():
                if target == r:
                    expanded_user_roles.add(alias)

        if not expanded_user_roles.intersection(normalized_required):
            raise QuantError(
                "AUTH_FORBIDDEN",
                f"Access forbidden: role '{user_role}' lacks required role from {required_roles}",
                status_code=403,
            )
        return user

    return _role_guard


def require_permission(required_permissions: list[str] | str) -> Callable:
    """FastAPI dependency factory enforcing that the authenticated user has all specified permission keys."""
    if isinstance(required_permissions, str):
        required_permissions = [required_permissions]

    req_set = set(required_permissions)

    async def _permission_guard(request: Request, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        user_role = (user.get("role") or "").lower()
        user_roles = {r.lower() for r in user.get("roles", [])}
        if user_role:
            user_roles.add(user_role)

        # Admin superuser always bypasses
        if "admin" in user_roles:
            return user

        # Aggregate user permissions from explicit claims + role matrix
        user_perms = set(user.get("permissions", []))
        for r in user_roles:
            user_perms.update(get_permissions_for_role(r))

        if not req_set.issubset(user_perms):
            missing = list(req_set - user_perms)
            raise QuantError(
                "AUTH_FORBIDDEN",
                f"Access forbidden: missing required permissions {missing}",
                status_code=403,
            )
        return user

    return _permission_guard
