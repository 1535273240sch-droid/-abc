from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import get_audit_service, get_execution_service, get_order_service, get_reconciliation_service
from app.schemas.execution import (
    AdapterExecuteResponse,
    CancelRequest,
    CancelResponse,
    FillRequest,
    FillResponse,
    ReconciliationLogResponse,
    ReconciliationRunResponse,
    ResolutionRequest,
    ResolutionResponse,
)
from app.services.audit_service import AuditService
from app.services.order_execution_service import OrderExecutionService
from app.services.order_service import OrderService
from app.services.reconciliation_service import ReconciliationService

router = APIRouter(prefix="/api/v1/execution", tags=["Execution"])


@router.post("/fills", response_model=FillResponse)
async def record_fill(
    body: FillRequest,
    request: Request,
    exec_service: OrderExecutionService = Depends(get_execution_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    result = exec_service.fill(
        client_order_id=body.client_order_id,
        fill_quantity=body.fill_quantity,
        fill_price=body.fill_price,
    )
    order = result["order"]
    fill = result["fill"]
    pos_updates = result["position_updates"]

    trace_id = getattr(request.state, "request_id", None)
    audit_service.record(
        event_type="order.filled",
        actor=order.account_id,
        resource_type="order",
        resource_id=order.client_order_id,
        details={
            "fill_id": fill.fill_id,
            "fill_quantity": fill.fill_quantity,
            "fill_price": fill.fill_price,
            "status": order.status.value,
            "filled_quantity": order.filled_quantity,
            "position_updates": pos_updates,
        },
        ip_address=request.client.host if request.client else None,
        trace_id=trace_id,
    )

    return FillResponse(
        client_order_id=order.client_order_id,
        fill_id=fill.fill_id,
        status=order.status.value,
        filled_quantity=order.filled_quantity,
        average_price=order.average_price,
        position_updates=pos_updates,
    )


@router.post("/orders/{client_order_id}/cancel", response_model=CancelResponse)
async def cancel_order(
    client_order_id: str,
    body: CancelRequest,
    request: Request,
    exec_service: OrderExecutionService = Depends(get_execution_service),
    audit_service: AuditService = Depends(get_audit_service),
    order_service: OrderService = Depends(get_order_service),
):
    order = exec_service.cancel(client_order_id=client_order_id)

    trace_id = getattr(request.state, "request_id", None)
    audit_service.record(
        event_type="order.status_changed",
        actor=order.account_id,
        resource_type="order",
        resource_id=order.client_order_id,
        details={"status": order.status.value, "filled_quantity": order.filled_quantity},
        ip_address=request.client.host if request.client else None,
        trace_id=trace_id,
    )

    return CancelResponse(
        client_order_id=order.client_order_id,
        status=order.status.value,
        reject_reason=order.reject_reason,
    )


@router.post("/orders/{client_order_id}/reject", response_model=CancelResponse)
async def reject_order(
    client_order_id: str,
    body: CancelRequest,
    request: Request,
    exec_service: OrderExecutionService = Depends(get_execution_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    order = exec_service.reject(client_order_id=client_order_id, reason="Manual rejection")

    trace_id = getattr(request.state, "request_id", None)
    audit_service.record(
        event_type="order.status_changed",
        actor=order.account_id,
        resource_type="order",
        resource_id=order.client_order_id,
        details={"status": order.status.value, "reason": order.reject_reason},
        ip_address=request.client.host if request.client else None,
        trace_id=trace_id,
    )

    return CancelResponse(
        client_order_id=order.client_order_id,
        status=order.status.value,
        reject_reason=order.reject_reason,
    )


@router.post("/orders/{client_order_id}/execute", response_model=AdapterExecuteResponse)
async def execute_order_via_adapter(
    client_order_id: str,
    request: Request,
    exec_service: OrderExecutionService = Depends(get_execution_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    trace_id = getattr(request.state, "request_id", None)
    result = exec_service.execute_via_adapter(
        client_order_id=client_order_id,
        trace_id=trace_id,
    )
    order = result["order"]
    fill = result["fill"]
    pos_updates = result["position_updates"]
    adapter_result = result["adapter_result"]

    audit_service.record(
        event_type="order.filled",
        actor=order.account_id,
        resource_type="order",
        resource_id=order.client_order_id,
        details={
            "source": "adapter",
            "exchange": adapter_result["exchange"],
            "fill_quantity": order.filled_quantity,
            "status": order.status.value,
            "position_updates": pos_updates,
        },
        ip_address=request.client.host if request.client else None,
        trace_id=trace_id,
    )

    return AdapterExecuteResponse(
        client_order_id=order.client_order_id,
        fill_id=fill.fill_id if fill else None,
        status=order.status.value,
        filled_quantity=order.filled_quantity,
        average_price=order.average_price,
        position_updates=pos_updates,
        adapter_result=adapter_result,
    )


@router.post("/reconciliation", response_model=ReconciliationRunResponse)
async def run_reconciliation(
    request: Request,
    account_id: str = Query("paper-main"),
    reconciliation_service: ReconciliationService = Depends(get_reconciliation_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    log = reconciliation_service.run(account_id=account_id)

    trace_id = getattr(request.state, "request_id", None)
    audit_service.record(
        event_type="reconciliation.ran",
        actor=account_id,
        resource_type="reconciliation",
        resource_id=log.reconciliation_id,
        details={"status": log.status.value, "details": log.details, "summary": log.summary},
        ip_address=request.client.host if request.client else None,
        trace_id=trace_id,
    )

    return ReconciliationRunResponse(
        reconciliation_id=log.reconciliation_id,
        account_id=log.account_id,
        status=log.status.value,
        details=log.details,
        summary=log.summary,
        created_at=log.created_at,
    )


@router.get("/reconciliation", response_model=list[ReconciliationLogResponse])
async def list_reconciliation_logs(
    account_id: str | None = Query(None),
    reconciliation_service: ReconciliationService = Depends(get_reconciliation_service),
):
    logs = reconciliation_service.get_logs(account_id=account_id)
    return [
        ReconciliationLogResponse(
            reconciliation_id=l.reconciliation_id,
            account_id=l.account_id,
            status=l.status.value,
            details=l.details,
            summary=l.summary,
            created_at=l.created_at,
        )
        for l in logs
    ]


@router.post("/reconciliation/{reconciliation_id}/resolution", response_model=ResolutionResponse)
async def record_resolution(
    reconciliation_id: str,
    body: ResolutionRequest,
    request: Request,
    reconciliation_service: ReconciliationService = Depends(get_reconciliation_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    record = reconciliation_service.resolve(
        reconciliation_id=reconciliation_id,
        decision=body.decision,
        reason=body.reason,
        actor=body.actor,
        mode=body.mode,
        idempotency_key=body.idempotency_key,
    )

    trace_id = getattr(request.state, "request_id", None)
    audit_service.record(
        event_type="reconciliation.resolved",
        actor=body.actor,
        resource_type="reconciliation_resolution",
        resource_id=record.resolution_id,
        details={
            "reconciliation_id": reconciliation_id,
            "decision": record.decision.value,
            "reason": record.reason,
            "mode": body.mode,
        },
        ip_address=request.client.host if request.client else None,
        trace_id=trace_id,
    )

    return ResolutionResponse(
        resolution_id=record.resolution_id,
        reconciliation_id=record.reconciliation_id,
        account_id=record.account_id,
        decision=record.decision.value,
        reason=record.reason,
        actor=record.actor,
        idempotency_key=record.idempotency_key,
        created_at=record.created_at,
    )