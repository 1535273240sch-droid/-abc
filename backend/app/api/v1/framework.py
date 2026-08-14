"""API endpoints for the pluggable strategy framework.

Exposes:
- GET  /api/v1/framework/strategies          — catalog of registered strategies
- GET  /api/v1/framework/strategies/{kind}   — single strategy metadata + param schema
- POST /api/v1/framework/run                 — trigger one evaluation tick (paper dry-run)
- GET  /api/v1/framework/klines/status       — kline service buffer status
- POST /api/v1/framework/klines/refresh      — pull latest klines for given symbols
"""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.errors import QuantError
from app.db.memory import get_store
from app.strategies import autodiscover, registry
from app.strategies.runtime import FrameworkRunner

router = APIRouter(prefix="/api/v1/framework", tags=["strategy-framework"])

_discovered = False


def _ensure_discovered() -> None:
    global _discovered
    if not _discovered:
        autodiscover()
        _discovered = True


class RunRequest(BaseModel):
    kind: str = Field(..., description="registered strategy kind, e.g. dual_ma")
    params: dict[str, Any] = Field(default_factory=dict)
    strategy_id: str = Field(default="framework-manual")
    account_id: str = Field(default="paper-main")
    dry_run: bool = Field(default=True, description="true = signals only, no order intents")


class KlineRefreshRequest(BaseModel):
    symbols: list[str] = Field(..., description=["BTCUSDT"])
    period: str = Field(default="1h")
    limit: int = Field(default=200, ge=1, le=1000)


@router.get("/strategies")
def list_strategies() -> dict[str, Any]:
    _ensure_discovered()
    return {"strategies": registry.catalog(), "count": len(registry.kinds())}


@router.get("/strategies/{kind}")
def get_strategy(kind: str) -> dict[str, Any]:
    _ensure_discovered()
    cls = registry.get(kind)
    if cls is None:
        raise QuantError("NOT_FOUND", f"strategy kind '{kind}' not registered", status_code=404)
    for item in registry.catalog():
        if item["kind"] == kind:
            return item
    raise QuantError("NOT_FOUND", f"strategy kind '{kind}' catalog missing", status_code=404)


@router.post("/run")
def run_strategy(req: RunRequest) -> dict[str, Any]:
    _ensure_discovered()
    store = get_store()
    try:
        strategy = registry.create(req.kind, req.params)
    except KeyError as exc:
        raise QuantError("NOT_FOUND", str(exc), status_code=404) from exc
    except ValueError as exc:
        raise QuantError("VALIDATION_ERROR", str(exc), status_code=400) from exc

    runner = FrameworkRunner(store)
    report = runner.run_once(
        strategy,
        strategy_id=req.strategy_id,
        account_id=req.account_id,
        mode="paper",
        dry_run=req.dry_run,
    )
    store.save()
    return report


@router.get("/klines/status")
def kline_status() -> dict[str, Any]:
    store = get_store()
    svc = getattr(store, "kline_service", None)
    if svc is None:
        raise QuantError("NOT_FOUND", "kline service not initialised", status_code=404)
    return svc.status()


@router.post("/klines/refresh")
def kline_refresh(req: KlineRefreshRequest) -> dict[str, Any]:
    store = get_store()
    svc = getattr(store, "kline_service", None)
    if svc is None:
        raise QuantError("NOT_FOUND", "kline service not initialised", status_code=404)
    updated = svc.refresh_symbols(req.symbols, req.period, req.limit)
    return {"updated": updated, "period": req.period}
