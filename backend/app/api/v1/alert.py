from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_alert_service
from app.schemas.alert import AlertResponse
from app.services.alert_service import AlertService

router = APIRouter(prefix="/api/v1/alerts", tags=["Alerts"])


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    status: str | None = Query(None),
    service: AlertService = Depends(get_alert_service),
):
    return service.list_alerts(status=status)
