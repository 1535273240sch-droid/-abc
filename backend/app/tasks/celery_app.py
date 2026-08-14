"""Celery application for async task processing.

Celery is used for:
  - Scheduled strategy execution (periodic beat)
  - Market data refresh (batch polling)
  - Reconciliation jobs
  - Alert processing & notification dispatch

Usage:
  # Start worker
  celery -A app.tasks.celery_app worker --loglevel=info

  # Start beat scheduler
  celery -A app.tasks.celery_app beat --loglevel=info
"""

from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    from celery import Celery

    celery_app = Celery(
        "quant_system",
        broker=settings.celery_broker_url or "redis://localhost:6379/1",
        backend=settings.celery_result_backend or "redis://localhost:6379/2",
    )

    celery_app.conf.update(
        # Serialisation
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",

        # Timezone
        timezone="UTC",
        enable_utc=True,

        # Reliability
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_default_retry_delay=30,
        task_max_retries=3,

        # Performance
        worker_prefetch_multiplier=1,
        worker_max_tasks_per_child=1000,
        task_time_limit=300,        # 5 min hard limit
        task_soft_time_limit=240,  # 4 min soft limit

        # Beat schedule
        beat_schedule={
            "strategy-scheduler": {
                "task": "app.tasks.tasks.run_scheduled_strategies",
                "schedule": max(30, settings.strategy_scheduler_interval_seconds),
            },
            "market-refresh": {
                "task": "app.tasks.tasks.refresh_market_data",
                "schedule": max(5, settings.market_refresh_seconds),
            },
            "reconciliation": {
                "task": "app.tasks.tasks.run_reconciliation",
                "schedule": 300,  # every 5 minutes
            },
            "approval-expiry-sweep": {
                "task": "app.tasks.tasks.sweep_expired_approvals",
                "schedule": 120,  # every 2 minutes
            },
        },

        # DLQ
        task_routes={
            "app.tasks.tasks.*": {"queue": "quant_default"},
        },
    )

    logger.info("Celery app configured (broker=%s)", celery_app.conf.broker_url)

except ImportError:
    celery_app = None
    logger.warning("Celery not installed; async tasks disabled")
