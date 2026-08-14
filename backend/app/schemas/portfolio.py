from datetime import datetime

from pydantic import BaseModel


class PortfolioTargetRequest(BaseModel):
    account_id: str = "paper-main"
    strategy_id: str
    strategy_version: str
    symbol: str
    target_quantity: str
    target_weight: str | None = None
    mode: str = "paper"
    idempotency_key: str | None = None


class PortfolioTargetResponse(BaseModel):
    target_id: str
    account_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    target_quantity: str
    current_quantity: str
    delta: str
    target_weight: str | None = None
    mode: str
    idempotency_key: str | None = None
    created_at: datetime
    updated_at: datetime