from datetime import datetime

from pydantic import BaseModel


class AlertResponse(BaseModel):
    alert_id: str
    severity: str
    source: str
    code: str
    status: str
    first_seen_at: datetime
    last_seen_at: datetime
    details: dict
