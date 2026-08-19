"""Authentication and User Management REST API endpoints."""

from __future__ import annotations

import hmac
import time
from fastapi import APIRouter, Depends, Header, Request

from app.core.api_key import extract_bearer_token
from app.core.auth import (
    ROLE_PERMISSIONS,
    ROLE_PERMISSIONS_MAP,
    authenticate_user,
    create_access_token,
    create_refresh_token,
    create_user,
    get_current_user,
    get_permissions_for_role,
    get_user,
    verify_access_token,
    verify_password,
    verify_token,
)
from app.core.config import settings
from app.core.errors import QuantError
from app.schemas.auth import (
    AuthStatusResponse,
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    RegisterRequest,
    RegisterResponse,
    UserResponse,
)


router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(request: Request, authorization: str | None = Header(None)):
    """Retrieve current authentication service status and caller profile if authenticated."""
    current_user = None
    auth_header = authorization or request.headers.get("Authorization")
    if auth_header:
        scheme, token = extract_bearer_token(auth_header)
        if scheme == "bearer" and token:
            claims = verify_access_token(token)
            if claims:
                current_user = {
                    "username": claims.get("username", claims.get("sub")),
                    "role": claims.get("role"),
                    "roles": claims.get("roles", [claims.get("role")]),
                    "permissions": claims.get("permissions", []),
                }

    supported_roles = ["trader", "risk_admin", "auditor", "admin", "quant", "risk_officer", "viewer"]
    return AuthStatusResponse(
        enabled=settings.auth_enabled,
        provider="local-hmac-jwt",
        algorithm="HS256",
        supported_roles=supported_roles,
        timestamp=int(time.time()),
        user=current_user,
    )


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(body: RegisterRequest):
    """Register a new user with secure salted password hashing and role assignment."""
    username = body.username.strip()
    if not username:
        raise QuantError("INVALID_USERNAME", "Username cannot be empty", status_code=400)

    # Check for duplicate user
    if get_user(username) or (settings.auth_admin_username and username == settings.auth_admin_username):
        raise QuantError("USER_ALREADY_EXISTS", f"User '{username}' already exists", status_code=409)

    # Validate requested role
    role_norm = (body.role or "trader").lower()
    if role_norm == "admin":
        raise QuantError("FORBIDDEN_ROLE", "Admin role cannot be self-registered", status_code=403)
    if role_norm not in ROLE_PERMISSIONS and role_norm not in ROLE_PERMISSIONS_MAP:
        raise QuantError("INVALID_ROLE", f"Role '{role_norm}' is invalid. Supported: {list(ROLE_PERMISSIONS_MAP.keys())}", status_code=400)

    user = create_user(
        username=username,
        password=body.password,
        role=role_norm,
        permissions=body.permissions,
        email=body.email,
    )

    token = create_access_token(username=username, role=role_norm, permissions=user["permissions"])
    refresh_token = create_refresh_token(username=username, role=role_norm)

    return RegisterResponse(
        user_id=user["user_id"],
        username=username,
        role=role_norm,
        roles=user["roles"],
        permissions=user["permissions"],
        access_token=str(token),
        refresh_token=str(refresh_token),
        token_type="bearer",
        expires_at=token.expires_at,
        created_at=user["created_at"],
    )


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """Authenticate user credentials and issue RFC 7519 HS256 Access & Refresh Tokens."""
    if not settings.auth_enabled:
        raise QuantError("AUTH_DISABLED", "Authentication is disabled for this environment", status_code=409)

    user_dict = authenticate_user(body.username, body.password)
    if not user_dict:
        # Check system admin fallback configured in environment
        if settings.auth_admin_password and hmac.compare_digest(body.username, settings.auth_admin_username):
            if hmac.compare_digest(body.password, settings.auth_admin_password) or verify_password(body.password, settings.auth_admin_password):
                user_dict = {
                    "username": body.username,
                    "role": "admin",
                    "roles": ["admin"],
                    "permissions": list(ROLE_PERMISSIONS_MAP["admin"]),
                }

    if not user_dict:
        raise QuantError("AUTH_INVALID_CREDENTIALS", "Invalid username or password", status_code=401)

    role = user_dict.get("role", "trader")
    roles = user_dict.get("roles", [role])
    permissions = user_dict.get("permissions", list(get_permissions_for_role(role)))
    username = user_dict.get("username", body.username)

    token = create_access_token(username=username, role=role, permissions=permissions)
    refresh_token = create_refresh_token(username=username, role=role)

    return LoginResponse(
        access_token=str(token),
        refresh_token=str(refresh_token),
        token_type="bearer",
        expires_at=token.expires_at,
        username=username,
        role=role,
        roles=roles,
        permissions=permissions,
    )


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token_endpoint(body: RefreshTokenRequest):
    """Renew an expired access token using a valid, unexpired refresh token."""
    refresh_token_str = body.refresh_token.strip()
    if not refresh_token_str:
        raise QuantError("AUTH_REQUIRED", "Refresh token string is required", status_code=400)

    claims = verify_token(refresh_token_str, token_type="refresh")
    if not claims:
        # Also attempt verification if type claim was omitted
        claims = verify_token(refresh_token_str)

    if not claims:
        raise QuantError("AUTH_INVALID_TOKEN", "Refresh token is invalid or expired", status_code=401)

    username = claims.get("username") or claims.get("sub")
    role = claims.get("role", "trader")

    # Check user active state
    user = get_user(username)
    if user and not user.get("is_active", True):
        raise QuantError("USER_INACTIVE", "User account is deactivated", status_code=403)

    roles = user["roles"] if user else claims.get("roles", [role])
    permissions = user["permissions"] if user else claims.get("permissions", list(get_permissions_for_role(role)))

    new_access_token = create_access_token(username=username, role=role, permissions=permissions)
    new_refresh_token = create_refresh_token(username=username, role=role)

    return LoginResponse(
        access_token=str(new_access_token),
        refresh_token=str(new_refresh_token),
        token_type="bearer",
        expires_at=new_access_token.expires_at,
        username=username,
        role=role,
        roles=roles,
        permissions=permissions,
    )


@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    """Retrieve detailed identity and permissions of the currently authenticated user."""
    username = current_user.get("username") or current_user.get("sub")
    user = get_user(username)
    if user:
        return UserResponse(
            user_id=user["user_id"],
            username=user["username"],
            role=user["role"],
            roles=user["roles"],
            permissions=user["permissions"],
            is_active=user.get("is_active", True),
            created_at=user.get("created_at", 0),
            email=user.get("email"),
        )

    return UserResponse(
        user_id=f"usr_{username}",
        username=username,
        role=current_user.get("role", "trader"),
        roles=current_user.get("roles", [current_user.get("role", "trader")]),
        permissions=current_user.get("permissions", []),
        is_active=True,
        created_at=current_user.get("iat", int(time.time())),
        email=None,
    )
