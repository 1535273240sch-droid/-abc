from typing import Any
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.core.dependencies import get_alert_service
from app.db.memory import get_store
from app.schemas.alert import AlertResponse
from app.services.alert_service import AlertService
from app.services.alert_notification_service import AlertNotificationService, AlertLevel

router = APIRouter(prefix="/api/v1/alerts", tags=["Alerts"])


class SendAlertRequest(BaseModel):
    title: str = Field(..., description="Alert title")
    message: str = Field(..., description="Alert message content")
    level: str = Field("warning", description="Severity level: info, warning, error, critical")
    channels: list[str] | None = Field(None, description="Optional target channels")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata or context")
    source: str = Field("manual", description="Alert trigger source")


class ConfigureChannelRequest(BaseModel):
    channel: str = Field(..., description="Channel name: wechat_work, feishu, dingtalk, telegram, email")
    config: dict[str, Any] = Field(..., description="Channel specific configuration dictionary")


def get_alert_notification_service(request: Request) -> AlertNotificationService:
    store = get_store(request)
    return store.alert_notification_service


@router.get("/status")
async def get_alert_status(
    service: AlertNotificationService = Depends(get_alert_notification_service),
):
    return service.status()


@router.post("/send")
@router.post("/test")
async def send_alert(
    req: SendAlertRequest,
    service: AlertNotificationService = Depends(get_alert_notification_service),
):
    record = service.alert(
        title=req.title,
        message=req.message,
        severity=req.level,
        source=req.source,
        details=req.metadata,
        channels=req.channels,
    )
    return {
        "status": "success",
        "alert_id": record["alert_id"],
        "channels": record["channels"],
    }


@router.post("/config")
async def configure_alert_channel(
    req: ConfigureChannelRequest,
    service: AlertNotificationService = Depends(get_alert_notification_service),
):
    service.configure_channel(req.channel, req.config)
    return {
        "status": "success",
        "channel": req.channel,
        "current_status": service.status(),
    }


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    status: str | None = Query(None),
    service: AlertService = Depends(get_alert_service),
):
    return service.list_alerts(status=status)
