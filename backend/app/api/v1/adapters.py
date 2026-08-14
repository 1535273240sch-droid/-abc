"""Read-only adapter status and simulation endpoints.

These endpoints expose adapter connection state and standardized market data.
They do NOT create orders, bypass risk preflight, or bypass kill switch.
"""

from fastapi import APIRouter, Depends, Request

from app.core.dependencies import get_adapter_service, get_audit_service, get_kill_switch_service
from app.schemas.adapters import (
    AdapterConnectResponse,
    AdapterHealthResponse,
    AdapterSymbolResponse,
    AdapterTickerResponse,
)
from app.services.audit_service import AuditService
from app.services.kill_switch_service import KillSwitchService

router = APIRouter(prefix="/api/v1/adapters", tags=["Adapters"])


@router.get("", response_model=list[AdapterHealthResponse])
async def list_adapters(
    adapter_service=Depends(get_adapter_service),
):
    adapters = adapter_service.list_adapters()
    return [AdapterHealthResponse(**a) for a in adapters]


@router.get("/{name}", response_model=AdapterHealthResponse)
async def get_adapter(
    name: str,
    adapter_service=Depends(get_adapter_service),
):
    from app.core.errors import QuantError

    adapter = adapter_service.get_adapter(name)
    if not adapter:
        raise QuantError("NOT_FOUND", f"Adapter {name} not found", status_code=404)
    return AdapterHealthResponse(**adapter)


@router.post("/{name}/connect", response_model=AdapterConnectResponse)
async def connect_adapter(
    name: str,
    request: Request,
    adapter_service=Depends(get_adapter_service),
    audit_service: AuditService = Depends(get_audit_service),
    ks_service: KillSwitchService = Depends(get_kill_switch_service),
):
    from app.core.errors import QuantError

    ks_service.assert_not_active("connect adapter")
    result = adapter_service.connect(name)
    if not result:
        raise QuantError("NOT_FOUND", f"Adapter {name} not found", status_code=404)

    trace_id = getattr(request.state, "request_id", None)
    audit_service.record(
        event_type="adapter.connected",
        actor="system",
        resource_type="adapter",
        resource_id=name,
        details={"status": result["status"]},
        ip_address=request.client.host if request.client else None,
        trace_id=trace_id,
    )
    return AdapterConnectResponse(**result)


@router.post("/{name}/disconnect", response_model=AdapterConnectResponse)
async def disconnect_adapter(
    name: str,
    request: Request,
    adapter_service=Depends(get_adapter_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    from app.core.errors import QuantError

    result = adapter_service.disconnect(name)
    if not result:
        raise QuantError("NOT_FOUND", f"Adapter {name} not found", status_code=404)

    trace_id = getattr(request.state, "request_id", None)
    audit_service.record(
        event_type="adapter.disconnected",
        actor="system",
        resource_type="adapter",
        resource_id=name,
        details={"status": result["status"]},
        ip_address=request.client.host if request.client else None,
        trace_id=trace_id,
    )
    return AdapterConnectResponse(**result)


@router.get("/{name}/symbols", response_model=list[AdapterSymbolResponse])
async def get_adapter_symbols(
    name: str,
    adapter_service=Depends(get_adapter_service),
):
    from app.core.errors import QuantError

    symbols = adapter_service.get_adapter_symbols(name)
    if symbols is None:
        raise QuantError("NOT_FOUND", f"Adapter {name} not found", status_code=404)
    return [AdapterSymbolResponse(**s.__dict__) for s in symbols]


@router.get("/{name}/tickers/{symbol}", response_model=AdapterTickerResponse)
async def get_adapter_ticker(
    name: str,
    symbol: str,
    adapter_service=Depends(get_adapter_service),
):
    from app.core.errors import QuantError

    ticker = adapter_service.get_adapter_ticker(name, symbol)
    if ticker is None:
        raise QuantError("NOT_FOUND", f"Adapter {name} or symbol {symbol} not found", status_code=404)
    return AdapterTickerResponse(
        symbol=ticker.symbol,
        source=ticker.source,
        last_price=ticker.last_price,
        bid_price=ticker.bid_price,
        ask_price=ticker.ask_price,
        volume_24h=ticker.volume_24h,
        event_time=ticker.event_time.isoformat(),
        sequence=ticker.sequence,
    )