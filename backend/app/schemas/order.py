from datetime import datetime

from pydantic import BaseModel, Field


class OrderIntentRequest(BaseModel):
    client_order_id: str
    account_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    market_type: str = "spot"
    side: str
    order_type: str = "limit"
    quantity: str
    limit_price: str | None = None
    mode: str = "paper"
    risk_decision_id: str


class OrderResponse(BaseModel):
    client_order_id: str
    account_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    market_type: str
    side: str
    order_type: str
    quantity: str
    limit_price: str | None = None
    mode: str
    risk_decision_id: str | None = None
    status: str
    filled_quantity: str
    average_price: str | None = None
    reject_reason: str | None = None
    created_at: datetime
    updated_at: datetime