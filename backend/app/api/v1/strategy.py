from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import get_audit_service, get_strategy_runtime_service, get_strategy_service
from app.schemas.strategy import StrategyCreateRequest, StrategyResponse, StrategyUpdateRequest
from app.schemas.strategy_runtime import StrategyRunRequest, StrategyRunResponse
from app.services.audit_service import AuditService
from app.services.strategy_service import StrategyService
from app.services.strategy_runtime_service import StrategyRuntimeService

router = APIRouter(prefix="/api/v1/strategies", tags=["Strategies"])


def _run_response(run) -> StrategyRunResponse:
    return StrategyRunResponse(
        run_id=run.run_id,
        strategy_id=run.strategy_id,
        strategy_version=run.strategy_version,
        account_id=run.account_id,
        mode=run.mode.value,
        dry_run=run.dry_run,
        status=run.status,
        data_quality=run.data_quality,
        signals=run.signals,
        orders=run.orders,
        reason=run.reason,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


@router.get("/runs", response_model=list[StrategyRunResponse])
async def list_strategy_runs(
    strategy_id: str | None = Query(None),
    runtime_service: StrategyRuntimeService = Depends(get_strategy_runtime_service),
):
    return [_run_response(run) for run in runtime_service.list_runs(strategy_id=strategy_id)]


@router.post("/scheduler/run")
async def trigger_strategy_scheduler(
    runtime_service: StrategyRuntimeService = Depends(get_strategy_runtime_service),
):
    count = runtime_service.run_scheduled()
    return {
        "status": "completed",
        "strategies_run": count,
        "dry_run": True,
        "last_run_at": runtime_service.scheduler_last_run_at,
    }


@router.post("/{strategy_id}/run", response_model=StrategyRunResponse, status_code=201)
async def run_strategy(
    strategy_id: str,
    body: StrategyRunRequest,
    request: Request,
    runtime_service: StrategyRuntimeService = Depends(get_strategy_runtime_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    run = runtime_service.run(
        strategy_id=strategy_id,
        account_id=body.account_id,
        mode=body.mode,
        dry_run=body.dry_run,
    )
    audit_service.record(
        event_type="strategy.run_completed",
        actor=body.account_id,
        resource_type="strategy_run",
        resource_id=run.run_id,
        details={"strategy_id": strategy_id, "status": run.status, "dry_run": body.dry_run, "orders": run.orders},
        ip_address=request.client.host if request.client else None,
        trace_id=getattr(request.state, "request_id", None),
    )
    return _run_response(run)


@router.get("", response_model=list[StrategyResponse])
async def list_strategies(
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    strategies = strategy_service.get_strategies()
    return [
        StrategyResponse(
            strategy_id=s.strategy_id,
            name=s.name,
            version=s.version,
            description=s.description,
            parameters=s.parameters,
            code_ref=s.code_ref,
            owner=s.owner,
            kind=s.kind,
            status=s.status,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in strategies
    ]


@router.post("", response_model=StrategyResponse, status_code=201)
async def create_strategy(
    body: StrategyCreateRequest,
    request: Request,
    strategy_service: StrategyService = Depends(get_strategy_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    s = strategy_service.create(
        strategy_id=body.strategy_id,
        name=body.name,
        version=body.version,
        description=body.description,
        parameters=body.parameters,
        code_ref=body.code_ref,
        owner=body.owner,
        kind=body.kind,
    )

    trace_id = getattr(request.state, "request_id", None)
    audit_service.record(
        event_type="strategy.created",
        actor=body.owner or "system",
        resource_type="strategy",
        resource_id=s.strategy_id,
        details={"version": s.version, "code_ref": s.code_ref},
        ip_address=request.client.host if request.client else None,
        trace_id=trace_id,
    )

    return StrategyResponse(
        strategy_id=s.strategy_id,
        name=s.name,
        version=s.version,
        description=s.description,
        parameters=s.parameters,
        code_ref=s.code_ref,
        owner=s.owner,
        kind=s.kind,
        status=s.status,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: str,
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    from app.core.errors import QuantError
    s = strategy_service.get(strategy_id)
    if not s:
        raise QuantError("NOT_FOUND", f"Strategy {strategy_id} not found", status_code=404)
    return StrategyResponse(
        strategy_id=s.strategy_id,
        name=s.name,
        version=s.version,
        description=s.description,
        parameters=s.parameters,
        code_ref=s.code_ref,
        owner=s.owner,
        kind=s.kind,
        status=s.status,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.patch("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: str,
    body: StrategyUpdateRequest,
    request: Request,
    strategy_service: StrategyService = Depends(get_strategy_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    s = strategy_service.update(
        strategy_id=strategy_id,
        name=body.name,
        version=body.version,
        description=body.description,
        parameters=body.parameters,
        code_ref=body.code_ref,
        owner=body.owner,
        kind=body.kind,
        status=body.status,
    )

    trace_id = getattr(request.state, "request_id", None)
    audit_service.record(
        event_type="strategy.updated",
        actor=s.owner or "system",
        resource_type="strategy",
        resource_id=s.strategy_id,
        details={"version": s.version, "code_ref": s.code_ref, "status": s.status},
        ip_address=request.client.host if request.client else None,
        trace_id=trace_id,
    )

    return StrategyResponse(
        strategy_id=s.strategy_id,
        name=s.name,
        version=s.version,
        description=s.description,
        parameters=s.parameters,
        code_ref=s.code_ref,
        owner=s.owner,
        kind=s.kind,
        status=s.status,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )
