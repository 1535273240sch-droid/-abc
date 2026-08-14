from datetime import datetime

from pydantic import BaseModel


class ApprovalCreateRequest(BaseModel):
    resource_type: str
    resource_id: str
    requested_by: str
    title: str
    details: str = ""


class ApprovalDecideRequest(BaseModel):
    decision: str
    decided_by: str
    reject_reason: str | None = None


class ApprovalResponse(BaseModel):
    approval_id: str
    resource_type: str
    resource_id: str
    requested_by: str
    title: str
    details: str
    status: str
    decided_by: str | None = None
    reject_reason: str | None = None
    created_at: datetime
    decided_at: datetime | None = None
    expires_at: datetime


class KillSwitchTriggerRequest(BaseModel):
    triggered_by: str
    reason: str


class KillSwitchRecoverRequest(BaseModel):
    recovered_by: str
    reason: str
    approval_id: str
    mode: str = "paper"


class KillSwitchStateResponse(BaseModel):
    status: str
    triggered_by: str | None = None
    trigger_reason: str | None = None
    triggered_at: datetime | None = None
    recovered_by: str | None = None
    recovered_at: datetime | None = None