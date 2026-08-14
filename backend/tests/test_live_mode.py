import os

os.environ.setdefault("QUANT_ENVIRONMENT", "test")
os.environ.setdefault("QUANT_AUTH_ENABLED", "false")
os.environ.setdefault("QUANT_ALLOWED_HOSTS", '["testserver", "localhost", "127.0.0.1", "0.0.0.0"]')
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
os.environ.setdefault("QUANT_LIVE_TRADING_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient

from app.db.memory import get_store
from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


class TestLiveRisk:
    def test_breaker_trips_after_threshold(self, client: TestClient):
        store = get_store()
        risk = store.live_risk_service
        for _ in range(30):
            risk.update_equity("paper-main", 100000)
        risk.update_equity("paper-main", 85000)
        assert risk.breaker_tripped is True

    def test_reset_clears_breaker(self, client: TestClient):
        store = get_store()
        risk = store.live_risk_service
        risk.reset_breaker("admin")
        assert risk.breaker_tripped is False

    def test_max_position_blocks_oversize(self, client: TestClient):
        store = get_store()
        risk = store.live_risk_service
        rules = risk.check_order("paper-main", "BTCUSDT", "buy", "100", "1000000")
        assert rules[-1]["rule"] == "live_max_position_value"
        assert rules[-1]["passed"] is False
