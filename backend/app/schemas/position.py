from pydantic import BaseModel


class MarkToMarketRequest(BaseModel):
    account_id: str = "paper-main"
    symbol: str
    mark_price: str
    mode: str = "paper"
    idempotency_key: str | None = None


class MarkToMarketResponse(BaseModel):
    account_id: str
    symbol: str
    mark_price: str
    positions_updated: int
    updates: list
    idempotency_key: str | None = None