from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import get_audit_service, get_portfolio_target_service
from app.schemas.portfolio import PortfolioTargetRequest, PortfolioTargetResponse
from app.services.audit_service import AuditService
from app.services.portfolio_service import PortfolioTargetService

router = APIRouter(prefix="/api/v1/portfolio", tags=["Portfolio"])


@router.post("/targets", response_model=PortfolioTargetResponse, status_code=201)
async def create_portfolio_target(
    body: PortfolioTargetRequest,
    request: Request,
    pt_service: PortfolioTargetService = Depends(get_portfolio_target_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    target = pt_service.set_target(
        account_id=body.account_id,
        strategy_id=body.strategy_id,
        strategy_version=body.strategy_version,
        symbol=body.symbol,
        target_quantity=body.target_quantity,
        target_weight=body.target_weight,
        mode=body.mode,
        idempotency_key=body.idempotency_key,
    )

    trace_id = getattr(request.state, "request_id", None)
    audit_service.record(
        event_type="portfolio.target_created",
        actor=body.account_id,
        resource_type="portfolio_target",
        resource_id=target.target_id,
        details={
            "symbol": target.symbol,
            "strategy_id": target.strategy_id,
            "target_quantity": target.target_quantity,
            "current_quantity": target.current_quantity,
            "delta": target.delta,
            "mode": target.mode.value,
        },
        ip_address=request.client.host if request.client else None,
        trace_id=trace_id,
    )

    return PortfolioTargetResponse(
        target_id=target.target_id,
        account_id=target.account_id,
        strategy_id=target.strategy_id,
        strategy_version=target.strategy_version,
        symbol=target.symbol,
        target_quantity=target.target_quantity,
        current_quantity=target.current_quantity,
        delta=target.delta,
        target_weight=target.target_weight,
        mode=target.mode.value,
        idempotency_key=target.idempotency_key,
        created_at=target.created_at,
        updated_at=target.updated_at,
    )


@router.get("/targets", response_model=list[PortfolioTargetResponse])
async def list_portfolio_targets(
    account_id: str | None = Query(None),
    pt_service: PortfolioTargetService = Depends(get_portfolio_target_service),
):
    targets = pt_service.list_targets(account_id=account_id)
    return [
        PortfolioTargetResponse(
            target_id=t.target_id,
            account_id=t.account_id,
            strategy_id=t.strategy_id,
            strategy_version=t.strategy_version,
            symbol=t.symbol,
            target_quantity=t.target_quantity,
            current_quantity=t.current_quantity,
            delta=t.delta,
            target_weight=t.target_weight,
            mode=t.mode.value,
            idempotency_key=t.idempotency_key,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in targets
    ]


@router.get("/targets/{target_id}", response_model=PortfolioTargetResponse)
async def get_portfolio_target(
    target_id: str,
    pt_service: PortfolioTargetService = Depends(get_portfolio_target_service),
):
    from app.core.errors import QuantError

    target = pt_service.get_target(target_id)
    if not target:
        raise QuantError("NOT_FOUND", f"Portfolio target {target_id} not found", status_code=404)
    return PortfolioTargetResponse(
        target_id=target.target_id,
        account_id=target.account_id,
        strategy_id=target.strategy_id,
        strategy_version=target.strategy_version,
        symbol=target.symbol,
        target_quantity=target.target_quantity,
        current_quantity=target.current_quantity,
        delta=target.delta,
        target_weight=target.target_weight,
        mode=target.mode.value,
        idempotency_key=target.idempotency_key,
        created_at=target.created_at,
        updated_at=target.updated_at,
    )