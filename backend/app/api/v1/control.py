from fastapi import APIRouter, Depends, Request

from app.core.dependencies import get_audit_service, get_control_service
from app.schemas.control import (
    ExchangeConnectionResponse,
    ExchangeTestResponse,
    ExchangeConnectionUpsertRequest,
    ModelProviderResponse,
    ModelProviderUpsertRequest,
    ProviderTestResponse,
)
from app.services.audit_service import AuditService
from app.services.control_service import ControlService

router = APIRouter(prefix="/api/v1/control", tags=["Control"])


@router.get("/model-providers", response_model=list[ModelProviderResponse])
async def list_model_providers(service: ControlService = Depends(get_control_service)):
    return service.list_model_providers()


@router.put("/model-providers/{provider_id}", response_model=ModelProviderResponse)
async def upsert_model_provider(
    provider_id: str,
    body: ModelProviderUpsertRequest,
    request: Request,
    service: ControlService = Depends(get_control_service),
    audit: AuditService = Depends(get_audit_service),
):
    payload = body.model_dump()
    payload["provider_id"] = provider_id
    provider = service.upsert_model_provider(payload)
    actor = getattr(request.state, "user", {}).get("sub", "system")
    audit.record("control.model_provider_updated", actor, "model_provider", provider_id, {"enabled": provider["enabled"], "secret_ref_present": bool(provider.get("secret_ref"))}, request.client.host if request.client else None, getattr(request.state, "request_id", None))
    return provider


@router.post("/model-providers/{provider_id}/test", response_model=ProviderTestResponse)
async def test_model_provider(provider_id: str, service: ControlService = Depends(get_control_service)):
    return service.test_model_provider(provider_id)


@router.get("/exchanges", response_model=list[ExchangeConnectionResponse])
async def list_exchange_connections(service: ControlService = Depends(get_control_service)):
    return service.list_exchange_connections()


@router.put("/exchanges/{connection_id}", response_model=ExchangeConnectionResponse)
async def upsert_exchange_connection(
    connection_id: str,
    body: ExchangeConnectionUpsertRequest,
    request: Request,
    service: ControlService = Depends(get_control_service),
    audit: AuditService = Depends(get_audit_service),
):
    payload = body.model_dump()
    payload["connection_id"] = connection_id
    connection = service.upsert_exchange_connection(payload)
    actor = getattr(request.state, "user", {}).get("sub", "system")
    audit.record("control.exchange_connection_updated", actor, "exchange_connection", connection_id, {"adapter_name": connection["adapter_name"], "environment": connection["environment"], "secret_ref_present": bool(connection.get("secret_ref"))}, request.client.host if request.client else None, getattr(request.state, "request_id", None))
    return connection


@router.post("/exchanges/{connection_id}/test", response_model=ExchangeTestResponse)
async def test_exchange_connection(
    connection_id: str,
    request: Request,
    service: ControlService = Depends(get_control_service),
    audit: AuditService = Depends(get_audit_service),
):
    result = service.test_exchange_connection(connection_id)
    actor = getattr(request.state, "user", {}).get("sub", "system")
    audit.record(
        "control.exchange_connection_tested",
        actor,
        "exchange_connection",
        connection_id,
        {"status": result["status"], "runtime_ready": result["runtime_ready"]},
        request.client.host if request.client else None,
        getattr(request.state, "request_id", None),
    )
    return result
