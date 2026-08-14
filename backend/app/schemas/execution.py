from datetime import datetime

from pydantic import BaseModel


class FillRequest(BaseModel):
    client_order_id: str
    fill_quantity: str
    fill_price: str


class FillResponse(BaseModel):
    client_order_id: str
    fill_id: str
    status: str
    filled_quantity: str
    average_price: str | None = None
    position_updates: dict | None = None


class CancelRequest(BaseModel):
    client_order_id: str


class CancelResponse(BaseModel):
    client_order_id: str
    status: str
    reject_reason: str | None = None


class ReconciliationRunResponse(BaseModel):
    reconciliation_id: str
    account_id: str
    status: str
    details: str
    summary: dict
    created_at: datetime


class ReconciliationLogResponse(BaseModel):
    reconciliation_id: str
    account_id: str
    status: str
    details: dict
    summary: dict
    created_at: datetime


class AdapterExecuteResponse(BaseModel):
    client_order_id: str
    fill_id: str | None = None
    status: str
    filled_quantity: str
    average_price: str | None = None
    position_updates: dict | None = None
    adapter_result: dict | None = None


class ResolutionRequest(BaseModel):
    decision: str
    reason: str
    actor: str
    mode: str = "paper"
    idempotency_key: str | None = None


class ResolutionResponse(BaseModel):
    resolution_id: str
    reconciliation_id: str
    account_id: str
    decision: str
    reason: str
    actor: str
    idempotency_key: str | None = None
    created_at: datetime