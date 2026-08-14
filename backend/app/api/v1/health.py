from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.db.memory import get_store
from app.events.bus import event_bus
router = APIRouter(tags=["Health"])

_start_time = datetime.now(timezone.utc)


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/ready")
async def ready():
    store = get_store()
    checks = {
        "storage": not bool(getattr(store, "persistence_error", None)),
        "auth": not settings.auth_enabled or bool(settings.auth_secret and settings.auth_admin_password),
        "event_bus": bool(event_bus.health().get("ready")),
    }
    status = "ready" if all(checks.values()) else "not_ready"
    payload = {"status": status, "timestamp": datetime.now(timezone.utc).isoformat(), "checks": checks}
    return JSONResponse(status_code=200 if status == "ready" else 503, content=payload)
