"""Analytics API: trading performance report endpoints."""

from typing import Any

from fastapi import APIRouter, Query

from app.db.memory import get_store

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.get("/performance")
def get_performance_report(days: int = Query(90, ge=7, le=365)) -> dict[str, Any]:
    """Return the aggregated PnL performance report."""
    store = get_store()
    svc = getattr(store, "performance_analytics_service", None)
    if svc is None:
        from app.services.performance_analytics_service import PerformanceAnalyticsService

        svc = PerformanceAnalyticsService(store)
    return svc.get_performance_report(days=days)
