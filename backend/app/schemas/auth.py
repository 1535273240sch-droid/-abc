"""Authentication and RBAC request/response schemas."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128, description="Username for login")
    password: str = Field(min_length=1, max_length=512, description="Plaintext password")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, description="Unique username")
    password: str = Field(min_length=6, max_length=128, description="User password")
    role: str = Field(default="trader", description="Assigned RBAC role: trader, risk_admin, auditor, admin")
    permissions: list[str] | None = Field(default=None, description="Optional custom permissions list")
    email: str | None = Field(default=None, max_length=255, description="Optional user email")


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1, description="Valid refresh token string")


class LoginResponse(BaseModel):
    access_token: str = Field(description="RFC 7519 HS256 JWT access token")
    refresh_token: str | None = Field(default=None, description="Refresh token for renewing access")
    token_type: str = Field(default="bearer", description="Token type, standard bearer")
    expires_at: int = Field(description="Unix timestamp expiration of access token")
    username: str = Field(description="Authenticated username")
    role: str = Field(description="Primary RBAC role")
    roles: list[str] = Field(default_factory=list, description="All assigned roles")
    permissions: list[str] = Field(default_factory=list, description="Granted permission keys")


class RegisterResponse(BaseModel):
    user_id: str = Field(description="Unique generated user ID")
    username: str = Field(description="Registered username")
    role: str = Field(description="Assigned role")
    roles: list[str] = Field(default_factory=list, description="Assigned roles")
    permissions: list[str] = Field(default_factory=list, description="Granted permissions")
    access_token: str = Field(description="Initial access token")
    refresh_token: str | None = Field(default=None, description="Initial refresh token")
    token_type: str = Field(default="bearer")
    expires_at: int = Field(description="Expiration timestamp")
    created_at: int = Field(description="Registration timestamp")


class UserResponse(BaseModel):
    user_id: str
    username: str
    role: str
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: int = 0
    email: str | None = None


class AuthStatusResponse(BaseModel):
    enabled: bool
    provider: str
    algorithm: str = "HS256"
    supported_roles: list[str] = Field(default_factory=list)
    timestamp: int
    user: dict[str, Any] | None = None


class TokenData(BaseModel):
    sub: str | None = None
    username: str | None = None
    role: str | None = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    exp: int | None = None
    iat: int | None = None
    iss: str | None = None
    type: str | None = None
