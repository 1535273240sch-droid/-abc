from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import get_audit_service, get_position_service
from app.schemas.position import MarkToMarketRequest, MarkToMarketResponse
from app.services.audit_service import AuditService
from app.services.position_service import PositionService

router = APIRouter(prefix="/api/v1/positions", tags=["Positions"])


@router.get("")
async def list_positions(
    account_id: str | None = Query(None),
    position_service: PositionService = Depends(get_position_service),
):
    positions = position_service.get_positions(account_id=account_id)
    return [
        {
            "position_id": p.position_id,
            "account_id": p.account_id,
            "symbol": p.symbol,
            "market_type": p.market_type.value,
            "side": p.side.value,
            "quantity": p.quantity,
            "entry_price": p.entry_price,
            "current_price": p.current_price,
            "unrealized_pnl": p.unrealized_pnl,
            "realized_pnl": p.realized_pnl,
            "created_at": p.created_at.isoformat(),
            "updated_at": p.updated_at.isoformat(),
        }
        for p in positions
    ]


@router.post("/mark-to-market", response_model=MarkToMarketResponse)
async def mark_to_market(
    body: MarkToMarketRequest,
    request: Request,
    position_service: PositionService = Depends(get_position_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    result = position_service.mark_to_market(
        account_id=body.account_id,
        symbol=body.symbol,
        mark_price=body.mark_price,
        mode=body.mode,
        idempotency_key=body.idempotency_key,
    )

    trace_id = getattr(request.state, "request_id", None)
    audit_service.record(
        event_type="position.mtm_updated",
        actor=body.account_id,
        resource_type="position",
        resource_id=f"{body.account_id}:{body.symbol}",
        details={
            "symbol": body.symbol,
            "mark_price": body.mark_price,
            "positions_updated": result["positions_updated"],
            "mode": body.mode,
        },
        ip_address=request.client.host if request.client else None,
        trace_id=trace_id,
    )

    return MarkToMarketResponse(
        account_id=result["account_id"],
        symbol=result["symbol"],
        mark_price=result["mark_price"],
        positions_updated=result["positions_updated"],
        updates=result["updates"],
        idempotency_key=result.get("idempotency_key"),
    )