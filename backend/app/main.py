import asyncio
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from app.adapters.protocol import AdapterError, ConnectionErrorAdapter, RateLimitError, RetryExhaustedError
from app.api.v1 import adapters, agent, ai, alert, audit, auth, control, execution, framework, governance, live, market, order, portfolio, position, research, risk, strategy, system
from app.core.api_key import extract_bearer_token, verify_api_key
from app.core.auth import role_allows, verify_access_token
from app.core.config import settings, validate_runtime_settings
from app.core.errors import QuantError, error_response, generic_error_handler, quant_error_handler
from app.core.logging import setup_logging, bind_request_context, clear_request_context, get_logger
from app.core.rate_limit import get_rate_limiter, _get_client_id
from app.db.memory import get_store
from app.observability.health import router as health_router
from app.services.okx_market_stream import OkxMarketStreamService
from app.observability.metrics import metrics
from app.observability.tracing import setup_tracing, shutdown_tracing, get_tracer

# Initialise structured logging & tracing at import time
setup_logging()
setup_tracing()

logger = get_logger(__name__)


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


validate_runtime_settings()
logger.info("application starting", version=settings.app_version, environment=settings.environment, mode=settings.mode)


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
    store.save()
    refresh_task = None
    strategy_scheduler_task = None
    okx_stream_task = None
    # OKX real-time market data line (public WS, no credentials required)
    if getattr(settings, "okx_stream_enabled", True):
        store.okx_market_stream = OkxMarketStreamService(store, demo=getattr(settings, "okx_stream_demo", False))

        async def okx_stream_loop():
            await store.okx_market_stream.run_forever()

        okx_stream_task = asyncio.create_task(okx_stream_loop())
    if settings.market_data_mode == "public":
        async def refresh_market_loop():
            while True:
                try:
                    await asyncio.to_thread(store.market_service.refresh_public_tickers)
                except Exception as exc:  # noqa: BLE001
                    store.market_service.record_refresh_error(exc)
                await asyncio.sleep(max(5, settings.market_refresh_seconds))

        refresh_task = asyncio.create_task(refresh_market_loop())
    if settings.strategy_scheduler_enabled:
        async def strategy_scheduler_loop():
            while True:
                await asyncio.sleep(max(30, settings.strategy_scheduler_interval_seconds))
                try:
                    await asyncio.to_thread(store.strategy_runtime_service.run_scheduled)
                except Exception as exc:  # noqa: BLE001
                    store.strategy_runtime_service.scheduler_error = str(exc)[:500]

        strategy_scheduler_task = asyncio.create_task(strategy_scheduler_loop())
    yield
    shutdown_tracing()
    logger.info("application shutting down")
    if okx_stream_task is not None:
        store.okx_market_stream.stop()
        okx_stream_task.cancel()
        await asyncio.gather(okx_stream_task, return_exceptions=True)
    if refresh_task is not None:
        refresh_task.cancel()
        await asyncio.gather(refresh_task, return_exceptions=True)
    if strategy_scheduler_task is not None:
        strategy_scheduler_task.cancel()
        await asyncio.gather(strategy_scheduler_task, return_exceptions=True)
    store.save()


docs_url = "/docs" if (settings.environment.lower() not in {"production", "prod"} or settings.debug) else None
redoc_url = "/redoc" if (settings.environment.lower() not in {"production", "prod"} or settings.debug) else None
openapi_url = "/openapi.json" if (settings.environment.lower() not in {"production", "prod"} or settings.debug) else None

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
)

if settings.allowed_hosts != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
if settings.force_https:
    app.add_middleware(HTTPSRedirectMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

app.add_exception_handler(QuantError, quant_error_handler)
app.add_exception_handler(AdapterError, adapter_error_handler)
app.add_exception_handler(Exception, generic_error_handler)

# OpenTelemetry auto-instrumentation (optional)
if settings.otel_enabled:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        pass


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    # Bind request context for structured logging
    bind_request_context(request_id, path=request.url.path, method=request.method)
    start = time.perf_counter()

    # ── Rate limiting ──
    limiter = get_rate_limiter()
    if limiter is not None and request.url.path.startswith("/api/v1"):
        client_id = _get_client_id(request)
        if asyncio.iscoroutinefunction(limiter.allow):
            allowed = await limiter.allow(client_id)
        else:
            allowed = limiter.allow(client_id)
        if not allowed:
            clear_request_context()
            return JSONResponse(
                status_code=429,
                content=error_response("RATE_LIMITED", "Rate limit exceeded", trace_id=request_id),
                headers={"Retry-After": "60"},
            )

    # ── Authentication ──
    protected_path = request.url.path.startswith("/api/v1") or (
        request.url.path == "/metrics" and settings.metrics_auth_enabled
    )
    if settings.auth_enabled and protected_path:
        public_paths = {"/api/v1/auth/status", "/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh"}
        if request.url.path not in public_paths:
            scheme, token = extract_bearer_token(request.headers.get("Authorization"))
            claims = None
            if scheme == "bearer" and token:
                claims = verify_access_token(token)
            elif scheme == "apikey" and token:
                claims = verify_api_key(token)
            if claims is None:
                clear_request_context()
                return JSONResponse(
                    status_code=401,
                    content=error_response("AUTH_REQUIRED", "A valid bearer token or API key is required", trace_id=request_id),
                )
            role = str(claims["role"])
            if not role_allows(role, request.method, request.url.path):
                clear_request_context()
                return JSONResponse(
                    status_code=403,
                    content=error_response("AUTH_FORBIDDEN", "The current role is not allowed to perform this action", trace_id=request_id),
                )
            request.state.user = claims

    # ── Tracing span ──
    tracer = get_tracer("app.http")
    with tracer.start_as_current_span("http_request") as span:
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.path", request.url.path)
        try:
            response = await call_next(request)
        except Exception:
            metrics.observe_error(request.url.path, "unhandled_exception")
            span.record_exception(__import__("sys").exc_info()[1])
            raise
        finally:
            get_store(request).save()

    elapsed_ms = (time.perf_counter() - start) * 1000
    metrics.observe_request(request.method, request.url.path, response.status_code, elapsed_ms)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{elapsed_ms / 1000:.4f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings.force_https:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    clear_request_context()
    return response


@app.get("/metrics", include_in_schema=False)
async def metrics_endpoint():
    if not settings.metrics_enabled:
        return PlainTextResponse("metrics disabled\n", status_code=404)
    return PlainTextResponse(metrics.prometheus(), media_type="text/plain; version=0.0.4")


app.include_router(health_router)
app.include_router(auth.router)
app.include_router(agent.router)
app.include_router(alert.router)
app.include_router(control.router)
app.include_router(ai.router)
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
app.include_router(framework.router)
app.include_router(live.router)
