from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_audit_service
from app.services.audit_service import AuditService

router = APIRouter(prefix="/api/v1/audit", tags=["Audit"])


@router.get("/events")
async def list_audit_events(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    audit_service: AuditService = Depends(get_audit_service),
):
    events = audit_service.get_events(limit=limit, offset=offset)
    return [
        {
            "event_id": e.event_id,
            "event_type": e.event_type,
            "actor": e.actor,
            "resource_type": e.resource_type,
            "resource_id": e.resource_id,
            "details": e.details,
            "ip_address": e.ip_address,
            "trace_id": e.trace_id,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]