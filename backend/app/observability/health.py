"""Enhanced health check with dependency probing.

Provides three endpoints:
  /health        — liveness probe (is the process running?)
  /health/ready  — readiness probe (are all dependencies ready?)
  /health/info   — system information (version, mode, uptime)
"""

from __future__ import annotations

import os
import time
import platform
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.db.memory import get_store

router = APIRouter(tags=["health"])

_start_time = time.time()


@router.get("/health")
@router.get("/health/")
async def liveness():
    """Liveness probe — returns 200 if the process is running."""
    return {"status": "ok", "timestamp": time.time()}


@router.get("/ready")
@router.get("/health/ready")
async def readiness(request: Request):
    """Readiness probe — checks all critical dependencies."""
    checks: dict[str, Any] = {}
    all_healthy = True

    # Check store
    try:
        store = get_store(request)
        checks["store"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["store"] = f"error: {str(exc)[:200]}"
        all_healthy = False

    # Check database (if configured)
    if settings.storage_backend == "postgres" and settings.postgres_dsn:
        try:
            from app.db.database import check_db_connection
            if check_db_connection():
                checks["database"] = "ok"
            else:
                checks["database"] = "unreachable"
                all_healthy = False
        except Exception as exc:  # noqa: BLE001
            checks["database"] = f"error: {str(exc)[:200]}"
            all_healthy = False

    # Check Redis (if configured)
    if settings.redis_url:
        try:
            import redis
            r = redis.from_url(settings.redis_url, socket_timeout=2)
            r.ping()
            checks["redis"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = f"error: {str(exc)[:200]}"
            all_healthy = False

    # Check kill switch
    try:
        store = get_store(request)
        ks = store.kill_switch_service.get_state()
        checks["kill_switch"] = ks.status.value
        if ks.status.value == "active":
            all_healthy = False
    except Exception:  # noqa: BLE001
        pass

    status_code = 200 if all_healthy else 503
    # Convert checks to boolean for backward compatibility
    checks_bool = {k: (v == "ok" if isinstance(v, str) else v) for k, v in checks.items()}
    # Map 'store' check to 'storage' for backward compatibility with tests
    if "store" in checks_bool:
        checks_bool["storage"] = checks_bool["store"]
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_healthy else "not_ready",
            "checks": checks_bool,
            "timestamp": time.time(),
        },
    )


@router.get("/health/info")
@router.get("/info")
async def system_info():
    """System information endpoint."""
    return {
        "app_name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "mode": settings.mode,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "uptime_seconds": round(time.time() - _start_time, 2),
        "pid": os.getpid(),
        "workers": 1,  # Updated by gunicorn when running with multiple workers
    }
