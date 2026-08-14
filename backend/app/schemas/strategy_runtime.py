from datetime import datetime

from pydantic import BaseModel, Field


class StrategyRunRequest(BaseModel):
    account_id: str = "paper-main"
    mode: str = "paper"
    dry_run: bool = True


class StrategyRunResponse(BaseModel):
    run_id: str
    strategy_id: str
    strategy_version: str
    account_id: str
    mode: str
    dry_run: bool
    status: str
    data_quality: dict
    signals: list[dict]
    orders: list[dict]
    reason: str | None = None
    created_at: datetime
    completed_at: datetime
