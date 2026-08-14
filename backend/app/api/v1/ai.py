from fastapi import APIRouter, Depends, Request

from app.core.dependencies import get_ai_service, get_audit_service
from app.schemas.ai import ChatRequest, ChatResponse
from app.services.ai_service import AIService
from app.services.audit_service import AuditService

router = APIRouter(prefix="/api/v1/ai", tags=["AI Runtime"])


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request, service: AIService = Depends(get_ai_service), audit: AuditService = Depends(get_audit_service)):
    result = service.chat(body.provider_id, [message.model_dump() for message in body.messages], body.temperature, body.max_tokens)
    actor = getattr(request.state, "user", {}).get("sub", "system")
    audit.record("ai.chat.completed", actor, "model_provider", body.provider_id, {"model": result["model"], "status": result["status"], "latency_ms": result["latency_ms"], "message_count": len(body.messages)}, request.client.host if request.client else None, getattr(request.state, "request_id", None))
    return result
