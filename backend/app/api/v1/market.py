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


_PERIOD_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


@router.get("/klines")
async def get_klines(
    symbol: str,
    period: str = Query("1h", pattern="^(1m|5m|15m|1h|4h|1d)$"),
    limit: int = Query(300, ge=10, le=1000),
):
    """OHLCV kline bars for the charting frontend (Binance public data, cached).

    Stale buffers (e.g. old imported backtest data) are auto-refreshed from the
    exchange when the newest bar is older than 3 periods.
    """
    import time as _time

    from app.db.memory import get_store

    store = get_store()
    svc = getattr(store, "kline_service", None)
    if svc is None:
        return []

    bars = svc.get_klines(symbol, period, count=limit)

    period_ms = _PERIOD_MS.get(period, 3_600_000)
    now_ms = int(_time.time() * 1000)
    if not bars or (now_ms - bars[-1].open_time) > (period_ms * 3 + 120_000):
        try:
            bars = svc.fetch_history(symbol, period, limit=min(max(limit, 100), 1000))
        except Exception:
            pass  # fall back to whatever the buffer holds

    return [
        {
            "timestamp": b.open_time,
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": float(b.volume),
        }
        for b in bars[-limit:]
    ]
