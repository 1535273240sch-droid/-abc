import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.adapters.protocol import AdapterError, ConnectionErrorAdapter, RateLimitError, RetryExhaustedError
from app.api.v1 import adapters, audit, execution, governance, health, market, order, portfolio, position, research, risk, strategy, system
from app.core.config import settings
from app.core.errors import QuantError, error_response, generic_error_handler, quant_error_handler
from app.db.memory import get_store


async def adapter_error_handler(request: Request, exc: AdapterError):
    from app.core.errors import _trace_id

    mapping = {
        ConnectionErrorAdapter: ("ADAPTER_NOT_CONNECTED", 503),
        RateLimitError: ("ADAPTER_RATE_LIMITED", 429),
        RetryExhaustedError: ("ADAPTER_RETRY_EXHAUSTED", 503),
    }
    code, status = mapping.get(type(exc), ("ADAPTER_ERROR", 503))
    return JSONResponse(
        status_code=status,
        content=error_response(code, exc.message, trace_id=_trace_id(request)),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = get_store()
    store.audit_service.record(
        event_type="system.startup",
        actor="system",
        resource_type="system",
        resource_id="app",
        details={"mode": settings.mode, "version": settings.app_version},
    )
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(QuantError, quant_error_handler)
app.add_exception_handler(AdapterError, adapter_error_handler)
app.add_exception_handler(Exception, generic_error_handler)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{time.perf_counter() - start:.4f}"
    return response


app.include_router(health.router)
app.include_router(system.router)
app.include_router(market.router)
app.include_router(risk.router)
app.include_router(order.router)
app.include_router(position.router)
app.include_router(research.router)
app.include_router(strategy.router)
app.include_router(adapters.router)
app.include_router(execution.router)
app.include_router(governance.router)
app.include_router(portfolio.router)
app.include_router(audit.router)