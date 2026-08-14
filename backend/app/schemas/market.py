from datetime import datetime

from pydantic import BaseModel


class SymbolResponse(BaseModel):
    symbol: str
    base_asset: str
    quote_asset: str
    market_type: str
    min_qty: str
    max_qty: str
    tick_size: str
    status: str


class TickerResponse(BaseModel):
    symbol: str
    last_price: str
    bid_price: str
    ask_price: str
    volume_24h: str
    change_24h: str
    high_24h: str
    low_24h: str
    source: str = "unknown"
    event_time: datetime | None = None
    ingest_time: datetime | None = None
    sequence: int | None = None


class MarketQualityResponse(BaseModel):
    status: str
    usable: bool
    checked_at: datetime
    symbol_count: int
    ticker_count: int
    issues: list[dict]


class OrderBookResponse(BaseModel):
    symbol: str
    source: str
    updated_at: datetime
    bids: list[list[str]]
    asks: list[list[str]]


class TradeResponse(BaseModel):
    trade_id: str
    symbol: str
    price: str
    quantity: str
    side: str
    time: datetime


class FundingRateResponse(BaseModel):
    symbol: str
    rate: str
    predicted_rate: str
    next_settlement: str
    open_interest: str
    open_interest_change: str
    source: str
