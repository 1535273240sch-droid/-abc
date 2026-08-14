from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import get_approval_service, get_audit_service, get_kill_switch_service
from app.schemas.governance import (
    ApprovalCreateRequest,
    ApprovalDecideRequest,
    ApprovalResponse,
    KillSwitchRecoverRequest,
    KillSwitchStateResponse,
    KillSwitchTriggerRequest,
)
from app.services.approval_service import ApprovalService
from app.services.audit_service import AuditService
from app.services.kill_switch_service import KillSwitchService

router = APIRouter(prefix="/api/v1/governance", tags=["Governance"])


@router.post("/approvals", response_model=ApprovalResponse, status_code=201)
async def create_approval(
    body: ApprovalCreateRequest,
    request: Request,
    approval_service: ApprovalService = Depends(get_approval_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    approval = approval_service.create(
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        requested_by=body.requested_by,
        title=body.title,
        details=body.details,
    )

    trace_id = getattr(request.state, "request_id", None)
    audit_service.record(
        event_type="approval.created",
        actor=body.requested_by,
        resource_type="approval",
        resource_id=approval.approval_id,
        details={
            "resource_type": approval.resource_type.value,
            "resource_id": approval.resource_id,
            "title": approval.title,
        },
        ip_address=request.client.host if request.client else None,
        trace_id=trace_id,
    )

    return ApprovalResponse(
        approval_id=approval.approval_id,
        resource_type=approval.resource_type.value,
        resource_id=approval.resource_id,
        requested_by=approval.requested_by,
        title=approval.title,
        details=approval.details,
        status=approval.status.value,
        created_at=approval.created_at,
        expires_at=approval.expires_at,
    )


@router.post("/approvals/{approval_id}/decide", response_model=ApprovalResponse)
async def decide_approval(
    approval_id: str,
    body: ApprovalDecideRequest,
    request: Request,
    approval_service: ApprovalService = Depends(get_approval_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    approval = approval_service.decide(
        approval_id=approval_id,
        decision=body.decision,
        decided_by=body.decided_by,
        reject_reason=body.reject_reason,
    )

    trace_id = getattr(request.state, "request_id", None)
    audit_service.record(
        event_type="approval.decided",
        actor=body.decided_by,
        resource_type="approval",
        resource_id=approval_id,
        details={
            "decision": approval.status.value,
            "reject_reason": approval.reject_reason,
            "resource_type": approval.resource_type.value,
            "resource_id": approval.resource_id,
        },
        ip_address=request.client.host if request.client else None,
        trace_id=trace_id,
    )

    return ApprovalResponse(
        approval_id=approval.approval_id,
        resource_type=approval.resource_type.value,
        resource_id=approval.resource_id,
        requested_by=approval.requested_by,
        title=approval.title,
        details=approval.details,
        status=approval.status.value,
        decided_by=approval.decided_by,
        reject_reason=approval.reject_reason,
        created_at=approval.created_at,
        decided_at=approval.decided_at,
        expires_at=approval.expires_at,
    )


@router.get("/approvals", response_model=list[ApprovalResponse])
async def list_approvals(
    status: str | None = Query(None),
    approval_service: ApprovalService = Depends(get_approval_service),
):
    approvals = approval_service.list_approvals(status=status)
    return [
        ApprovalResponse(
            approval_id=a.approval_id,
            resource_type=a.resource_type.value,
            resource_id=a.resource_id,
            requested_by=a.requested_by,
            title=a.title,
            details=a.details,
            status=a.status.value,
            decided_by=a.decided_by,
            reject_reason=a.reject_reason,
            created_at=a.created_at,
            decided_at=a.decided_at,
            expires_at=a.expires_at,
        )
        for a in approvals
    ]


@router.get("/approvals/{approval_id}", response_model=ApprovalResponse)
async def get_approval(
    approval_id: str,
    approval_service: ApprovalService = Depends(get_approval_service),
):
    approval = approval_service.get_approval(approval_id)
    if not approval:
        from app.core.errors import QuantError
        raise QuantError("NOT_FOUND", f"Approval {approval_id} not found", status_code=404)
    return ApprovalResponse(
        approval_id=approval.approval_id,
        resource_type=approval.resource_type.value,
        resource_id=approval.resource_id,
        requested_by=approval.requested_by,
        title=approval.title,
        details=approval.details,
        status=approval.status.value,
        decided_by=approval.decided_by,
        reject_reason=approval.reject_reason,
        created_at=approval.created_at,
        decided_at=approval.decided_at,
        expires_at=approval.expires_at,
    )


@router.post("/kill-switch/trigger", response_model=KillSwitchStateResponse)
async def trigger_kill_switch(
    body: KillSwitchTriggerRequest,
    request: Request,
    ks_service: KillSwitchService = Depends(get_kill_switch_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    state = ks_service.trigger(triggered_by=body.triggered_by, reason=body.reason)

    trace_id = getattr(request.state, "request_id", None)
    audit_service.record(
        event_type="kill_switch.triggered",
        actor=body.triggered_by,
        resource_type="kill_switch",
        resource_id="system",
        details={"reason": body.reason},
        ip_address=request.client.host if request.client else None,
        trace_id=trace_id,
    )

    return KillSwitchStateResponse(
        status=state.status.value,
        triggered_by=state.triggered_by,
        trigger_reason=state.trigger_reason,
        triggered_at=state.triggered_at,
    )


@router.post("/kill-switch/recover", response_model=KillSwitchStateResponse)
async def recover_kill_switch(
    body: KillSwitchRecoverRequest,
    request: Request,
    ks_service: KillSwitchService = Depends(get_kill_switch_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    state = ks_service.recover(recovered_by=body.recovered_by, reason=body.reason, approval_id=body.approval_id, mode=body.mode)

    trace_id = getattr(request.state, "request_id", None)
    audit_service.record(
        event_type="kill_switch.recovered",
        actor=body.recovered_by,
        resource_type="kill_switch",
        resource_id="system",
        details={"reason": body.reason},
        ip_address=request.client.host if request.client else None,
        trace_id=trace_id,
    )

    return KillSwitchStateResponse(
        status=state.status.value,
        triggered_by=state.triggered_by,
        trigger_reason=state.trigger_reason,
        triggered_at=state.triggered_at,
        recovered_by=state.recovered_by,
        recovered_at=state.recovered_at,
    )


@router.get("/kill-switch", response_model=KillSwitchStateResponse)
async def get_kill_switch_state(
    ks_service: KillSwitchService = Depends(get_kill_switch_service),
):
    state = ks_service.get_state()
    return KillSwitchStateResponse(
        status=state.status.value,
        triggered_by=state.triggered_by,
        trigger_reason=state.trigger_reason,
        triggered_at=state.triggered_at,
        recovered_by=state.recovered_by,
        recovered_at=state.recovered_at,
    )