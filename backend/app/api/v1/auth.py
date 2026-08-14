import time

from fastapi import APIRouter

from app.core.auth import authenticate, create_access_token
from app.core.config import settings
from app.core.errors import QuantError
from app.schemas.auth import LoginRequest, LoginResponse


router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


@router.get("/status")
async def auth_status():
    return {"enabled": settings.auth_enabled, "provider": "local-hmac", "timestamp": int(time.time())}


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    if not settings.auth_enabled:
        raise QuantError("AUTH_DISABLED", "Authentication is disabled for this environment", status_code=409)
    token = authenticate(body.username, body.password)
    if not token:
        raise QuantError("AUTH_INVALID_CREDENTIALS", "Invalid username or password", status_code=401)
    _, expires_at = create_access_token(body.username, "admin")
    return LoginResponse(access_token=token, expires_at=expires_at, username=body.username, role="admin")
