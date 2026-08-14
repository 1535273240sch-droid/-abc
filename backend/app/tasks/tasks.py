"""Celery task definitions for the quant system.

Each task is a thin wrapper around the existing service methods.
The heavy lifting stays in the service layer; these tasks only handle
scheduling, retry logic, and error reporting.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.tasks.run_scheduled_strategies", bind=True)
def run_scheduled_strategies(self: Any) -> dict:
    """Run all active strategies on their configured schedule."""
    try:
        from app.db.memory import reset_store, get_store
        # Get a fresh store instance for the worker process
        reset_store()
        store = get_store()
        store.strategy_runtime_service.run_scheduled()
        store.save()
        return {"status": "ok", "task": "run_scheduled_strategies"}
    except Exception as exc:  # noqa: BLE001
        logger.error("strategy scheduling failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="app.tasks.tasks.refresh_market_data", bind=True)
def refresh_market_data(self: Any) -> dict:
    """Refresh market tickers from external sources."""
    try:
        from app.db.memory import reset_store, get_store
        reset_store()
        store = get_store()
        if settings.market_data_mode == "public":
            store.market_service.refresh_public_tickers()
            store.save()
        return {"status": "ok", "task": "refresh_market_data"}
    except Exception as exc:  # noqa: BLE001
        logger.error("market refresh failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=10)


@celery_app.task(name="app.tasks.tasks.run_reconciliation", bind=True)
def run_reconciliation(self: Any, account_id: str = "paper-main") -> dict:
    """Run reconciliation for a given account."""
    try:
        from app.db.memory import reset_store, get_store
        reset_store()
        store = get_store()
        log = store.reconciliation_service.run(account_id=account_id)
        store.save()
        return {
            "status": "ok",
            "task": "run_reconciliation",
            "reconciliation_id": log.reconciliation_id,
            "result": log.status.value,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("reconciliation failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="app.tasks.tasks.sweep_expired_approvals", bind=True)
def sweep_expired_approvals(self: Any) -> dict:
    """Expire all pending approvals that have passed their TTL."""
    try:
        from app.db.memory import reset_store, get_store
        reset_store()
        store = get_store()
        expired = store.approval_service.expire_due()
        store.save()
        return {
            "status": "ok",
            "task": "sweep_expired_approvals",
            "expired_count": len(expired),
            "expired_ids": expired,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("approval sweep failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="app.tasks.tasks.execute_order", bind=True)
def execute_order(self: Any, client_order_id: str) -> dict:
    """Execute an order via the adapter (async wrapper)."""
    try:
        from app.db.memory import reset_store, get_store
        reset_store()
        store = get_store()
        result = store.execution_service.execute_via_adapter(
            client_order_id=client_order_id,
            trace_id=f"celery-{self.request.id}",
        )
        store.save()
        return {
            "status": "ok",
            "task": "execute_order",
            "order_id": client_order_id,
            "order_status": result["order"].status.value,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("order execution failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=5)


@celery_app.task(name="app.tasks.tasks.refresh_klines", bind=True)
def refresh_klines(self: Any, symbols: list | None = None, period: str = "1h", limit: int = 300) -> dict:
    """Refresh historical klines for the strategy framework."""
    try:
        from app.db.memory import reset_store, get_store
        reset_store()
        store = get_store()
        svc = getattr(store, "kline_service", None)
        if svc is None:
            return {"status": "skipped", "reason": "kline_service not initialised"}
        target = symbols or ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        updated = svc.refresh_symbols(target, period, limit)
        return {"status": "ok", "task": "refresh_klines", "updated": updated}
    except Exception as exc:  # noqa: BLE001
        logger.error("kline refresh failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="app.tasks.tasks.run_framework_strategies", bind=True)
def run_framework_strategies(self: Any) -> dict:
    """Run all registered framework strategies on their schedule (paper dry-run)."""
    try:
        from app.db.memory import reset_store, get_store
        from app.strategies import autodiscover, registry
        from app.strategies.runtime import FrameworkRunner
        reset_store()
        store = get_store()
        autodiscover()
        runner = FrameworkRunner(store)
        reports = []
        for kind in registry.kinds():
            try:
                strategy = registry.create(kind, {})
                report = runner.run_once(
                    strategy,
                    strategy_id=f"scheduled-{kind}",
                    account_id="paper-main",
                    mode="paper",
                    dry_run=True,
                )
                reports.append({"kind": kind, "signals": report["signal_count"]})
            except Exception as exc:  # noqa: BLE001
                logger.error("framework strategy %s failed: %s", kind, exc, exc_info=True)
                reports.append({"kind": kind, "error": str(exc)[:200]})
        store.save()
        return {"status": "ok", "task": "run_framework_strategies", "reports": reports}
    except Exception as exc:  # noqa: BLE001
        logger.error("framework scheduling failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=30)
