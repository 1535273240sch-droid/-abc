"""Test fixtures and test-environment isolation.

The application reads configuration from the ``QUANT_*`` environment variables
and a ``.env`` file. A deployed server ships a *production* ``.env``; if tests
loaded that, the middleware stack (TrustedHost whitelist, mandatory auth,
Postgres persistence, Redis events) would break the in-process TestClient.

To make ``pytest`` deterministic in any checkout, we force a dedicated test
configuration *before* importing the application module, so ``app.main`` builds
its app from these overrides rather than from a production ``.env``.
"""

import os

# Must be set before `app.main` is imported (importing app.main reads settings
# and constructs the FastAPI instance).
os.environ.setdefault("QUANT_ENVIRONMENT", "test")
os.environ.setdefault("QUANT_AUTH_ENABLED", "false")
os.environ.setdefault(
    "QUANT_ALLOWED_HOSTS",
    '["testserver", "localhost", "127.0.0.1", "0.0.0.0"]',
)
os.environ.setdefault("QUANT_FORCE_HTTPS", "false")
os.environ.setdefault("QUANT_STORAGE_ENABLED", "false")
os.environ.setdefault("QUANT_STORAGE_BACKEND", "pickle")
os.environ.setdefault("QUANT_MARKET_DATA_MODE", "mock")
os.environ.setdefault("QUANT_STRATEGY_SCHEDULER_ENABLED", "false")
os.environ.setdefault("QUANT_EVENT_BACKEND", "memory")
os.environ.setdefault("QUANT_METRICS_ENABLED", "false")
os.environ.setdefault("QUANT_METRICS_AUTH_ENABLED", "false")
os.environ.setdefault("QUANT_RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("QUANT_LOG_FORMAT", "text")
os.environ.setdefault("QUANT_OTEL_ENABLED", "false")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.memory import reset_store  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    reset_store()
    with TestClient(app) as c:
        yield c
    reset_store()


@pytest.fixture()
def approved_decision(client):
    resp = client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": "paper-main",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.01000000",
            "price": "99900.00",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
    )
    assert resp.status_code == 200
    return resp.json()