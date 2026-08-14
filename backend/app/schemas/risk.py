from pydantic import BaseModel, Field


class PreflightRequest(BaseModel):
    account_id: str
    symbol: str
    side: str
    quantity: str
    price: str
    strategy_id: str
    strategy_version: str
    mode: str = "paper"
    idempotency_key: str | None = None


class PreflightResponse(BaseModel):
    decision: str
    decision_id: str
    account_id: str
    symbol: str
    side: str
    quantity: str
    reject_reason: str | None = None
    remaining_risk_budget: str
    rules_checked: list[dict]
    mode: str
    # preflight 时的价格口径，用于下单时的名义价值核验
    price: str | None = None
    notional: str | None = None
    created_at: str