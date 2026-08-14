"""API Key management for service-to-service authentication.

API keys are HMAC-signed tokens that can be used instead of (or in
addition to) the standard JWT bearer tokens.  They are intended for
automated clients (trading bots, dashboards, CI/CD pipelines) that
need long-lived credentials.

Key format:  qak_<base64url(32 random bytes)>.<hmac_sha256(key, body)>
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Any

from app.core.config import settings


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def generate_api_key(name: str, role: str = "quant", ttl_days: int = 90) -> dict[str, Any]:
    """Generate a new API key.

    Returns a dict with:
      - key:       the full API key string (only shown once)
      - key_id:    public identifier (safe to store)
      - name:      human-readable label
      - role:      RBAC role
      - expires_at: unix timestamp
    """
    raw = os.urandom(32)
    key_id = _b64encode(os.urandom(8))
    body = _b64encode(raw)
    secret = settings.auth_secret.encode()
    message = f"qak.{key_id}.{body}".encode()
    signature = _b64encode(hmac.new(secret, message, hashlib.sha256).digest())

    full_key = f"qak.{key_id}.{body}.{signature}"
    expires_at = int(time.time()) + ttl_days * 86400

    return {
        "key": full_key,
        "key_id": key_id,
        "name": name,
        "role": role,
        "expires_at": expires_at,
    }


def verify_api_key(token: str) -> dict[str, Any] | None:
    """Verify an API key and return its claims, or None if invalid."""
    if not settings.auth_enabled or not settings.auth_secret:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 4 or parts[0] != "qak":
            return None
        _, key_id, body, signature = parts
        secret = settings.auth_secret.encode()
        message = f"qak.{key_id}.{body}".encode()
        expected = _b64encode(hmac.new(secret, message, hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        # In a production system, we would look up key_id in the database
        # to check if the key is still active and not revoked.
        # For now, any validly-signed key is accepted.
        return {"sub": key_id, "role": "quant", "exp": None, "type": "api_key"}
    except (ValueError, TypeError, IndexError):
        return None


def extract_bearer_token(authorization: str | None) -> tuple[str, str | None]:
    """Extract the scheme and token from an Authorization header.

    Returns (scheme, token) where scheme is "bearer" or "apikey".
    Returns ("", None) if the header is missing or malformed.
    """
    if not authorization:
        return "", None
    parts = authorization.split(" ", 1)
    if len(parts) != 2:
        return "", None
    scheme = parts[0].lower()
    token = parts[1].strip()
    if scheme == "bearer":
        if token.startswith("qak."):
            return "apikey", token
        return "bearer", token
    return scheme, token
