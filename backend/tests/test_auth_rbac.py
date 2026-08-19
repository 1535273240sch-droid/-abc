"""Comprehensive Test Suite for RFC 7519 JWT Authentication & RBAC Security (Milestone M4)."""

from __future__ import annotations

import base64
import json
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.auth import (
    authenticate,
    authenticate_user,
    create_access_token,
    create_refresh_token,
    create_user,
    get_permissions_for_role,
    get_user,
    hash_password,
    require_permission,
    require_role,
    reset_users,
    role_allows,
    verify_access_token,
    verify_password,
    verify_token,
)
from app.core.config import settings


@pytest.fixture(autouse=True)
def setup_auth_environment():
    """Ensure clean auth environment and reset in-memory user registry for each test."""
    reset_users()
    orig_enabled = settings.auth_enabled
    orig_secret = settings.auth_secret
    orig_admin_user = settings.auth_admin_username
    orig_admin_pass = settings.auth_admin_password
    orig_ttl = settings.auth_token_ttl_seconds

    settings.auth_enabled = True
    settings.auth_secret = "test_auth_secret_key_32_characters_long_12345"
    settings.auth_admin_username = "admin"
    settings.auth_admin_password = "AdminSuperSecretPassword123!"
    settings.auth_token_ttl_seconds = 3600

    yield

    reset_users()
    settings.auth_enabled = orig_enabled
    settings.auth_secret = orig_secret
    settings.auth_admin_username = orig_admin_user
    settings.auth_admin_password = orig_admin_pass
    settings.auth_token_ttl_seconds = orig_ttl


# ── 1. RFC 7519 Standard JWT Generation & Validation Tests ───────────────────

class TestJWTStandardHS256:
    def test_jwt_three_part_structure(self):
        token, expires_at = create_access_token("alice_trader", "trader")
        assert isinstance(token, str)
        parts = token.split(".")
        assert len(parts) == 3, "JWT must consist of header.payload.signature"

        # Verify header is valid JSON with alg=HS256 and typ=JWT
        header_raw = base64.urlsafe_b64decode(parts[0] + "=" * (-len(parts[0]) % 4))
        header = json.loads(header_raw.decode("utf-8"))
        assert header.get("alg") == "HS256"
        assert header.get("typ") == "JWT"

    def test_jwt_payload_standard_claims(self):
        token, expires_at = create_access_token(
            "bob_risk",
            role="risk_admin",
            expires_delta=timedelta(minutes=30),
        )
        claims = verify_access_token(token)
        assert claims is not None
        assert claims["sub"] == "bob_risk"
        assert claims["username"] == "bob_risk"
        assert claims["role"] == "risk_admin"
        assert "risk_admin" in claims["roles"]
        assert "risk:kill_switch" in claims["permissions"]
        assert claims["iss"] == "enterprise-quant-system"
        assert claims["type"] == "access"
        assert claims["exp"] == expires_at
        assert claims["iat"] <= int(time.time())

    def test_jwt_custom_dict_payload(self):
        custom_data = {
            "sub": "carol_auditor",
            "username": "carol",
            "role": "auditor",
            "custom_tag": "internal-audit",
        }
        token = create_access_token(custom_data, expires_delta=1800)
        assert isinstance(token, str)
        claims = verify_token(token)
        assert claims is not None
        assert claims["sub"] == "carol_auditor"
        assert claims["role"] == "auditor"
        assert claims["custom_tag"] == "internal-audit"
        assert "audit:view_logs" in claims["permissions"]

    def test_jwt_expiration_enforcement(self):
        # Create token that expired 10 seconds ago
        token = create_access_token("expired_user", "trader", expires_delta=-10)
        assert verify_access_token(token) is None
        assert verify_token(token) is None

    def test_jwt_tampered_payload_fails(self):
        token, _ = create_access_token("trader_dave", "trader")
        parts = token.split(".")
        # Tamper with payload by mutating characters
        tampered_payload = parts[1][:-2] + "ZX"
        tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"
        assert verify_access_token(tampered_token) is None

    def test_jwt_tampered_signature_fails(self):
        token, _ = create_access_token("trader_dave", "trader")
        parts = token.split(".")
        tampered_sig = parts[2][:-4] + "AAAA"
        tampered_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"
        assert verify_access_token(tampered_token) is None

    def test_jwt_refresh_token_lifecycle(self):
        refresh_token, exp = create_refresh_token("trader_eve", "trader")
        assert isinstance(refresh_token, str)
        claims = verify_token(refresh_token, token_type="refresh")
        assert claims is not None
        assert claims["sub"] == "trader_eve"
        assert claims["type"] == "refresh"
        assert claims["exp"] == exp

    def test_jwt_token_result_dual_interface(self):
        res = create_access_token("frank", "admin")
        # String interface
        assert isinstance(res, str)
        assert res.startswith("ey")
        # Tuple unpacking interface
        tok, exp = res
        assert tok == str(res)
        assert isinstance(exp, int)
        assert exp > int(time.time())


# ── 2. Password Security & PBKDF2-SHA256 Tests ──────────────────────────────

class TestPasswordHashingPBKDF2:
    def test_hash_password_format(self):
        hashed = hash_password("MySecurePassword123!")
        assert hashed.startswith("pbkdf2_sha256$100000$")
        parts = hashed.split("$")
        assert len(parts) == 4
        assert parts[1] == "100000"
        assert len(parts[2]) == 32  # 16 bytes hex salt
        assert len(parts[3]) == 64  # SHA256 hex digest

    def test_hash_password_unique_salts(self):
        pwd = "SamePasswordUsedTwice"
        hash1 = hash_password(pwd)
        hash2 = hash_password(pwd)
        assert hash1 != hash2, "Distinct salts must produce different hash outputs"

    def test_verify_password_valid(self):
        pwd = "CorrectHorseBatteryStaple!"
        hashed = hash_password(pwd)
        assert verify_password(pwd, hashed) is True

    def test_verify_password_invalid(self):
        pwd = "CorrectPassword"
        hashed = hash_password(pwd)
        assert verify_password("WrongPassword", hashed) is False
        assert verify_password("", hashed) is False

    def test_verify_password_edge_cases(self):
        assert verify_password("", "") is False
        assert verify_password("test", "corrupted_hash_format") is False
        assert verify_password("test", "pbkdf2_sha256$bad$salt$hash") is False


# ── 3. User Store & Authentication Logic Tests ──────────────────────────────

class TestUserStoreAndAuthenticate:
    def test_create_and_get_user(self):
        user = create_user(
            username="trader_sam",
            password="TraderPassword2026!",
            role="trader",
            email="sam@quant.internal",
        )
        assert user["username"] == "trader_sam"
        assert user["role"] == "trader"
        assert "order:create" in user["permissions"]
        assert user["email"] == "sam@quant.internal"

        fetched = get_user("trader_sam")
        assert fetched is not None
        assert fetched["user_id"] == user["user_id"]

    def test_authenticate_user_success(self):
        create_user("trader_lucy", "LucyPassword123!", role="trader")
        user = authenticate_user("trader_lucy", "LucyPassword123!")
        assert user is not None
        assert user["username"] == "trader_lucy"

    def test_authenticate_user_wrong_password(self):
        create_user("trader_lucy", "LucyPassword123!", role="trader")
        assert authenticate_user("trader_lucy", "WrongPassword") is None

    def test_authenticate_function_for_registered_user(self):
        create_user("risk_tom", "TomPassword123!", role="risk_admin")
        token = authenticate("risk_tom", "TomPassword123!")
        assert token is not None
        claims = verify_access_token(token)
        assert claims is not None
        assert claims["sub"] == "risk_tom"
        assert claims["role"] == "risk_admin"

    def test_authenticate_function_for_admin_config(self):
        token = authenticate("admin", "AdminSuperSecretPassword123!")
        assert token is not None
        claims = verify_access_token(token)
        assert claims is not None
        assert claims["sub"] == "admin"
        assert claims["role"] == "admin"


# ── 4. RBAC Roles & Fine-Grained Permissions Matrix Tests ────────────────────

class TestRBACPermissionsMatrix:
    def test_get_permissions_for_each_role(self):
        trader_perms = get_permissions_for_role("trader")
        assert "order:create" in trader_perms
        assert "order:cancel" in trader_perms
        assert "backtest:run" in trader_perms
        assert "risk:kill_switch" not in trader_perms
        assert "user:manage" not in trader_perms

        risk_perms = get_permissions_for_role("risk_admin")
        assert "risk:kill_switch" in risk_perms
        assert "position:liquidate" in risk_perms
        assert "audit:view_logs" in risk_perms
        assert "order:create" not in risk_perms

        auditor_perms = get_permissions_for_role("auditor")
        assert "audit:view_logs" in auditor_perms
        assert "trade:view_all" in auditor_perms
        assert "order:create" not in auditor_perms
        assert "risk:kill_switch" not in auditor_perms

        admin_perms = get_permissions_for_role("admin")
        assert "user:manage" in admin_perms
        assert "order:create" in admin_perms
        assert "risk:kill_switch" in admin_perms

    def test_role_aliases_mappings(self):
        assert get_permissions_for_role("quant") == get_permissions_for_role("trader")
        assert get_permissions_for_role("risk_officer") == get_permissions_for_role("risk_admin")
        assert get_permissions_for_role("viewer") == get_permissions_for_role("auditor")

    def test_role_allows_path_matrix(self):
        # Trader permissions
        assert role_allows("trader", "POST", "/api/v1/orders") is True
        assert role_allows("trader", "GET", "/api/v1/orders") is True
        assert role_allows("trader", "POST", "/api/v1/research") is True
        assert role_allows("trader", "GET", "/api/v1/governance") is False
        assert role_allows("trader", "GET", "/api/v1/control") is False

        # Risk Admin permissions
        assert role_allows("risk_admin", "GET", "/api/v1/governance") is True
        assert role_allows("risk_admin", "POST", "/api/v1/risk/kill-switch") is True
        assert role_allows("risk_admin", "GET", "/api/v1/audit") is True
        assert role_allows("risk_admin", "POST", "/api/v1/orders") is False

        # Auditor permissions (Read only)
        assert role_allows("auditor", "GET", "/api/v1/audit") is True
        assert role_allows("auditor", "GET", "/api/v1/orders") is True
        assert role_allows("auditor", "POST", "/api/v1/orders") is False
        assert role_allows("auditor", "DELETE", "/api/v1/orders") is False

        # Admin permissions (Full access)
        assert role_allows("admin", "GET", "/api/v1/control") is True
        assert role_allows("admin", "POST", "/api/v1/orders") is True
        assert role_allows("admin", "DELETE", "/api/v1/orders") is True
        assert role_allows("admin", "POST", "/api/v1/risk/kill-switch") is True


# ── 5. FastAPI RBAC Dependency Injection Unit Tests ─────────────────────────

class TestFastAPIRBACDependencies:
    @pytest.mark.asyncio
    async def test_require_role_dependency_matching_role(self):
        guard = require_role(["trader", "admin"])
        user_claims = {"sub": "alice", "role": "trader", "roles": ["trader"]}
        result = await guard(request=None, user=user_claims)
        assert result == user_claims

    @pytest.mark.asyncio
    async def test_require_role_dependency_denied_role(self):
        guard = require_role(["risk_admin"])
        user_claims = {"sub": "alice", "role": "trader", "roles": ["trader"]}
        with pytest.raises(Exception) as exc_info:
            await guard(request=None, user=user_claims)
        err = exc_info.value
        assert getattr(err, "status_code", None) == 403 or "forbidden" in str(err).lower()

    @pytest.mark.asyncio
    async def test_require_role_admin_override(self):
        guard = require_role(["auditor"])
        admin_claims = {"sub": "root", "role": "admin", "roles": ["admin"]}
        result = await guard(request=None, user=admin_claims)
        assert result == admin_claims

    @pytest.mark.asyncio
    async def test_require_permission_dependency_allowed(self):
        guard = require_permission(["order:create", "order:cancel"])
        user_claims = {
            "sub": "alice",
            "role": "trader",
            "roles": ["trader"],
            "permissions": ["order:create", "order:cancel", "trade:view_own"],
        }
        result = await guard(request=None, user=user_claims)
        assert result == user_claims

    @pytest.mark.asyncio
    async def test_require_permission_dependency_denied(self):
        guard = require_permission(["risk:kill_switch"])
        user_claims = {
            "sub": "alice",
            "role": "trader",
            "roles": ["trader"],
            "permissions": ["order:create", "order:cancel"],
        }
        with pytest.raises(Exception) as exc_info:
            await guard(request=None, user=user_claims)
        err = exc_info.value
        assert getattr(err, "status_code", None) == 403 or "forbidden" in str(err).lower()


# ── 6. REST API Endpoints Integration Tests (TestClient) ─────────────────────

class TestAuthAPIEndpoints:
    def test_auth_status_endpoint(self, client: TestClient):
        resp = client.get("/api/v1/auth/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["algorithm"] == "HS256"
        assert "trader" in data["supported_roles"]
        assert "risk_admin" in data["supported_roles"]

    def test_auth_status_with_bearer_token(self, client: TestClient):
        token, _ = create_access_token("status_tester", "auditor")
        resp = client.get(
            "/api/v1/auth/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"] is not None
        assert data["user"]["username"] == "status_tester"
        assert data["user"]["role"] == "auditor"

    def test_register_user_success(self, client: TestClient):
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": "new_trader_01",
                "password": "Password123456!",
                "role": "trader",
                "email": "new_trader@quant.com",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "new_trader_01"
        assert data["role"] == "trader"
        assert data["access_token"] is not None
        assert data["refresh_token"] is not None
        assert "order:create" in data["permissions"]

    def test_register_duplicate_username_fails(self, client: TestClient):
        client.post(
            "/api/v1/auth/register",
            json={"username": "duplicate_user", "password": "Password123!", "role": "trader"},
        )
        resp2 = client.post(
            "/api/v1/auth/register",
            json={"username": "duplicate_user", "password": "Password456!", "role": "trader"},
        )
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "USER_ALREADY_EXISTS"

    def test_register_invalid_role_fails(self, client: TestClient):
        resp = client.post(
            "/api/v1/auth/register",
            json={"username": "bad_role_user", "password": "Password123!", "role": "superuser_hacker"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_ROLE"

    def test_login_success_and_token_refresh(self, client: TestClient):
        # Register user
        reg_resp = client.post(
            "/api/v1/auth/register",
            json={"username": "login_user_01", "password": "SecurePassword999!", "role": "risk_admin"},
        )
        assert reg_resp.status_code == 201

        # Login
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": "login_user_01", "password": "SecurePassword999!"},
        )
        assert login_resp.status_code == 200
        login_data = login_resp.json()
        assert login_data["username"] == "login_user_01"
        assert login_data["role"] == "risk_admin"
        assert "risk:kill_switch" in login_data["permissions"]
        access_token = login_data["access_token"]
        refresh_token = login_data["refresh_token"]

        # Access /me profile with access_token
        me_resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["username"] == "login_user_01"
        assert me_resp.json()["role"] == "risk_admin"

        # Refresh token
        refresh_resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_resp.status_code == 200
        new_token_data = refresh_resp.json()
        assert new_token_data["access_token"] is not None
        assert new_token_data["refresh_token"] is not None

    def test_login_invalid_credentials_fails(self, client: TestClient):
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "non_existent_user", "password": "WrongPassword!"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"

    def test_refresh_with_invalid_token_fails(self, client: TestClient):
        resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "garbage.invalid.token"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "AUTH_INVALID_TOKEN"

    def test_me_profile_unauthenticated_fails(self, client: TestClient):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401


# ── 7. End-to-End RBAC Route Protection Verification ────────────────────────

class TestEndToEndRBACProtectedRoutes:
    def test_trader_can_access_orders_but_forbidden_on_governance(self, client: TestClient):
        trader_token, _ = create_access_token("trader_alex", "trader")
        headers = {"Authorization": f"Bearer {trader_token}"}

        # Trader can view orders
        resp_orders = client.get("/api/v1/orders", headers=headers)
        assert resp_orders.status_code in (200, 404)  # 200 list or standard response, not 401/403

        # Trader cannot access governance approvals
        resp_gov = client.get("/api/v1/governance/approvals", headers=headers)
        assert resp_gov.status_code == 403

    def test_risk_admin_can_access_governance_and_audit(self, client: TestClient):
        risk_token, _ = create_access_token("risk_rachel", "risk_admin")
        headers = {"Authorization": f"Bearer {risk_token}"}

        resp_gov = client.get("/api/v1/governance/approvals", headers=headers)
        assert resp_gov.status_code in (200, 404)

        resp_audit = client.get("/api/v1/audit", headers=headers)
        assert resp_audit.status_code in (200, 404)

    def test_auditor_cannot_mutate_state(self, client: TestClient):
        auditor_token, _ = create_access_token("auditor_arthur", "auditor")
        headers = {"Authorization": f"Bearer {auditor_token}"}

        # Auditor can read audit logs
        resp_audit = client.get("/api/v1/audit", headers=headers)
        assert resp_audit.status_code in (200, 404)

        # Auditor cannot post orders
        resp_post = client.post(
            "/api/v1/orders",
            json={"symbol": "BTC/USDT", "side": "buy", "order_type": "limit", "quantity": 1.0, "price": 50000.0},
            headers=headers,
        )
        assert resp_post.status_code == 403

    def test_admin_has_unrestricted_access(self, client: TestClient):
        admin_token, _ = create_access_token("super_admin", "admin")
        headers = {"Authorization": f"Bearer {admin_token}"}

        resp_control = client.get("/api/v1/control/status", headers=headers)
        assert resp_control.status_code in (200, 404)

        resp_gov = client.get("/api/v1/governance/approvals", headers=headers)
        assert resp_gov.status_code in (200, 404)
