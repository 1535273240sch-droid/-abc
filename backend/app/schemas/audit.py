from datetime import datetime

from pydantic import BaseModel, Field


class AuditEventResponse(BaseModel):
    event_id: str
    event_type: str
    actor: str
    resource_type: str
    resource_id: str
    details: dict
    ip_address: str | None = None
    created_at: datetime