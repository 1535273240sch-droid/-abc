from fastapi import Request
from fastapi.responses import JSONResponse


class ErrorCode:
    VALIDATION = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RISK_REJECTED = "RISK_REJECTED"
    RISK_REQUIRED = "RISK_DECISION_REQUIRED"
    INVALID_STATE = "INVALID_STATE"
    NOT_ALLOWED = "NOT_ALLOWED"
    INTERNAL = "INTERNAL_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    LIVE_TRADING_NOT_ALLOWED = "LIVE_TRADING_NOT_ALLOWED"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_ALREADY_DECIDED = "APPROVAL_ALREADY_DECIDED"
    ADAPTER_NOT_CONNECTED = "ADAPTER_NOT_CONNECTED"
    ADAPTER_RATE_LIMITED = "ADAPTER_RATE_LIMITED"
    ADAPTER_RETRY_EXHAUSTED = "ADAPTER_RETRY_EXHAUSTED"


class QuantError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, details: dict | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


def _trace_id(request: Request) -> str | None:
    return getattr(getattr(request, "state", None), "request_id", None)


def error_response(code: str, message: str, details: dict | None = None, trace_id: str | None = None) -> dict:
    body = {"error": {"code": code, "message": message, "details": details or {}}}
    if trace_id:
        body["error"]["trace_id"] = trace_id
    return body


async def quant_error_handler(request: Request, exc: QuantError):
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(exc.code, exc.message, exc.details, trace_id=_trace_id(request)),
    )


async def generic_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=error_response("INTERNAL_ERROR", "An unexpected error occurred", trace_id=_trace_id(request)),
    )