from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_market_service
from app.schemas.market import FundingRateResponse, MarketQualityResponse, OrderBookResponse, SymbolResponse, TickerResponse, TradeResponse
from app.services.market_service import MarketService

router = APIRouter(prefix="/api/v1/market", tags=["Market"])


@router.get("/symbols", response_model=list[SymbolResponse])
async def get_symbols(service: MarketService = Depends(get_market_service)):
    return [SymbolResponse.model_validate(s, from_attributes=True) for s in service.get_symbols()]


@router.get("/tickers", response_model=list[TickerResponse])
async def get_tickers(service: MarketService = Depends(get_market_service)):
    return [TickerResponse.model_validate(t, from_attributes=True) for t in service.get_tickers()]


@router.get("/quality", response_model=MarketQualityResponse)
async def get_market_quality(service: MarketService = Depends(get_market_service)):
    return service.sync_quality_alerts()


@router.get("/orderbook/{symbol}", response_model=OrderBookResponse)
async def get_order_book(symbol: str, depth: int = Query(5, ge=1, le=20), service: MarketService = Depends(get_market_service)):
    return service.get_order_book(symbol, depth=depth)


@router.get("/trades/{symbol}", response_model=list[TradeResponse])
async def get_trades(symbol: str, limit: int = Query(10, ge=1, le=20), service: MarketService = Depends(get_market_service)):
    return service.get_trades(symbol, limit=limit)


@router.get("/funding", response_model=list[FundingRateResponse])
async def get_funding_rates(service: MarketService = Depends(get_market_service)):
    return service.get_funding_rates()
