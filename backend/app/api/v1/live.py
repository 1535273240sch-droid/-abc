from fastapi import APIRouter, Depends, Request

from app.core.dependencies import get_audit_service, get_control_service, get_credential_service, get_live_mode_service, get_live_risk_service
from app.schemas.adapters import (
    CredentialRedactedResponse,
    CredentialSaveRequest,
    CredentialTestResponse,
    LiveDiagnosisResponse,
    LiveAuthorizationRequest,
    LiveRiskResetRequest,
    LiveRiskStatusResponse,
)
from app.services.audit_service import AuditService
from app.services.credential_service import CredentialService
from app.services.live_mode_service import LiveModeService
from app.services.live_risk_service import LiveRiskService

router = APIRouter(prefix="/api/v1/live", tags=["Live Trading"])


@router.get("/diagnosis", response_model=LiveDiagnosisResponse)
async def live_diagnosis(
    account_id: str = "paper-main",
    exchange: str | None = None,
    mode_service: LiveModeService = Depends(get_live_mode_service),
):
    return mode_service.diagnose(account_id=account_id, exchange=exchange)


@router.post("/authorization/request")
async def request_live_authorization(
    body: LiveAuthorizationRequest,
    request: Request,
    mode_service: LiveModeService = Depends(get_live_mode_service),
    audit: AuditService = Depends(get_audit_service),
):
    approval = mode_service.request_authorization(
        account_id=body.account_id,
        requested_by=getattr(request.state, "user", {}).get("sub", "system"),
        exchange=body.exchange,
        ttl_seconds=body.ttl_seconds,
    )
    actor = getattr(request.state, "user", {}).get("sub", "system")
    audit.record("live.authorization_requested", actor, "approval", approval.approval_id, {"exchange": body.exchange}, request.client.host if request.client else None, getattr(request.state, "request_id", None))
    return approval


@router.post("/authorization/revoke")
async def revoke_live_authorization(
    body: LiveAuthorizationRequest,
    request: Request,
    mode_service: LiveModeService = Depends(get_live_mode_service),
    audit: AuditService = Depends(get_audit_service),
):
    result = mode_service.revoke_authorization(body.account_id, operator=getattr(request.state, "user", {}).get("sub", "system"))
    audit.record("live.authorization_revoked", result["operator"], "account", body.account_id, {"revoked": result["revoked_approvals"]}, request.client.host if request.client else None, getattr(request.state, "request_id", None))
    return result


@router.get("/risk/status", response_model=LiveRiskStatusResponse)
async def live_risk_status(risk_service: LiveRiskService = Depends(get_live_risk_service)):
    return risk_service.status()


@router.post("/risk/reset")
async def reset_live_risk_breaker(
    body: LiveRiskResetRequest,
    request: Request,
    risk_service: LiveRiskService = Depends(get_live_risk_service),
    audit: AuditService = Depends(get_audit_service),
):
    result = risk_service.reset_breaker(operator=body.operator)
    audit.record("live.risk_breaker_reset", body.operator, "account", "paper-main", {"reset": result["reset"]}, request.client.host if request.client else None, getattr(request.state, "request_id", None))
    return result


@router.post("/credentials", response_model=CredentialRedactedResponse)
async def save_credentials(
    body: CredentialSaveRequest,
    request: Request,
    service: CredentialService = Depends(get_credential_service),
    audit: AuditService = Depends(get_audit_service),
):
    result = service.save(
        connection_id=body.connection_id,
        exchange=body.exchange,
        api_key=body.api_key,
        api_secret=body.api_secret,
        passphrase=body.passphrase,
        environment=body.environment,
        base_url=body.base_url,
        requested_by=getattr(request.state, "user", {}).get("sub", "system"),
    )
    audit.record("live.credentials_saved", getattr(request.state, "user", {}).get("sub", "system"), "exchange_connection", body.connection_id, {"exchange": body.exchange, "environment": body.environment}, request.client.host if request.client else None, getattr(request.state, "request_id", None))
    return result


@router.get("/credentials", response_model=list[CredentialRedactedResponse])
async def list_credentials(service: CredentialService = Depends(get_credential_service)):
    return service.list_credentials()


@router.get("/credentials/{connection_id}", response_model=CredentialRedactedResponse)
async def get_credential(connection_id: str, service: CredentialService = Depends(get_credential_service)):
    return service.redacted(connection_id)


@router.delete("/credentials/{connection_id}")
async def delete_credentials(
    connection_id: str,
    request: Request,
    service: CredentialService = Depends(get_credential_service),
    audit: AuditService = Depends(get_audit_service),
):
    result = service.delete(connection_id, operator=getattr(request.state, "user", {}).get("sub", "system"))
    audit.record("live.credentials_deleted", result["operator"], "exchange_connection", connection_id, {}, request.client.host if request.client else None, getattr(request.state, "request_id", None))
    return result


@router.post("/credentials/{connection_id}/test", response_model=CredentialTestResponse)
async def test_credentials(connection_id: str, service: CredentialService = Depends(get_credential_service)):
    return service.test(connection_id)
