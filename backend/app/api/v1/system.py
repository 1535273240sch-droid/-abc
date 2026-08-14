from datetime import datetime, timezone

from fastapi import APIRouter

from app.api.v1.health import _start_time
from app.core.config import settings
from app.db.memory import get_store
from app.observability.metrics import metrics
from app.events.bus import event_bus

router = APIRouter(prefix="/api/v1/system", tags=["System"])


@router.get("/status")
async def system_status():
    uptime = (datetime.now(timezone.utc) - _start_time).total_seconds()
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "mode": settings.mode,
        "uptime_seconds": uptime,
        "status": "running",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "storage": {
            "enabled": settings.storage_enabled,
            "backend": settings.storage_backend,
            "format": "quant-snapshot-v1" if settings.storage_enabled else None,
            "path": settings.storage_path if settings.storage_enabled and settings.storage_backend != "postgres" else None,
            "dsn_configured": bool(settings.postgres_dsn) if settings.storage_backend == "postgres" else False,
            "error": getattr(get_store(), "persistence_error", None),
        },
        "metrics": metrics.snapshot(),
        "events": event_bus.counts(),
        "event_bus": event_bus.health(),
        "market_data": get_store().market_service.health(),
        "alerts": get_store().alert_service.list_alerts(status="active"),
        "strategy_scheduler": {
            "enabled": settings.strategy_scheduler_enabled,
            "interval_seconds": settings.strategy_scheduler_interval_seconds,
            "last_run_at": get_store().strategy_runtime_service.scheduler_last_run_at,
            "runs": get_store().strategy_runtime_service.scheduler_runs,
            "last_error": get_store().strategy_runtime_service.scheduler_error,
        },
    }
