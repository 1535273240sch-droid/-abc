from fastapi import APIRouter, Depends, Request

from app.core.dependencies import get_audit_service, get_risk_service
from app.schemas.risk import PreflightRequest, PreflightResponse
from app.services.audit_service import AuditService
from app.services.risk_service import RiskService

router = APIRouter(prefix="/api/v1/risk", tags=["Risk"])


@router.post("/preflight", response_model=PreflightResponse)
async def risk_preflight(
    body: PreflightRequest,
    request: Request,
    risk_service: RiskService = Depends(get_risk_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    result = risk_service.preflight(
        account_id=body.account_id,
        symbol=body.symbol,
        side=body.side,
        quantity=body.quantity,
        price=body.price,
        strategy_id=body.strategy_id,
        strategy_version=body.strategy_version,
        mode=body.mode,
    )

    audit_service.record(
        event_type="risk.preflight",
        actor=body.account_id,
        resource_type="risk_decision",
        resource_id=result.decision_id,
        details={
            "decision": result.decision.value,
            "symbol": body.symbol,
            "side": body.side,
            "quantity": body.quantity,
            "mode": body.mode,
        },
        ip_address=request.client.host if request.client else None,
        trace_id=getattr(request.state, "request_id", None),
    )

    return PreflightResponse(
        decision=result.decision.value,
        decision_id=result.decision_id,
        account_id=result.account_id,
        symbol=result.symbol,
        side=result.side,
        quantity=result.quantity,
        reject_reason=result.reject_reason,
        remaining_risk_budget=result.remaining_risk_budget,
        rules_checked=result.rules_checked,
        mode=result.mode.value,
        price=getattr(result, "price", None),
        notional=getattr(result, "notional", None),
        created_at=result.created_at.isoformat(),
    )


@router.get("/rules")
async def get_risk_rules(risk_service: RiskService = Depends(get_risk_service)):
    return risk_service.rules()


@router.get("/circuit-breakers")
async def get_circuit_breakers(risk_service: RiskService = Depends(get_risk_service)):
    return risk_service.circuit_breakers()
