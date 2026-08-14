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

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.credential_crypto import CredentialCryptoError, open_dict, seal_dict
from app.db.memory import get_store
from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


class TestCredentialCrypto:
    def test_roundtrip(self):
        token = seal_dict("strong-master-key-here", {"api_key": "k", "api_secret": "s", "passphrase": "p"})
        out = open_dict("strong-master-key-here", token)
        assert out == {"api_key": "k", "api_secret": "s", "passphrase": "p"}

    def test_wrong_key(self):
        token = seal_dict("strong-master-key-here", {"api_key": "k", "api_secret": "s"})
        with pytest.raises(CredentialCryptoError):
            open_dict("wrong-key", token)

    def test_tampered_token(self):
        token = seal_dict("strong-master-key-here", {"api_key": "k", "api_secret": "s"})
        raw = token[:-4] + ("a" if token[-4] != "a" else "b") + token[-3:]
        with pytest.raises(CredentialCryptoError):
            open_dict("strong-master-key-here", raw)

    def test_short_key(self):
        with pytest.raises(CredentialCryptoError):
            seal_dict("short", {"api_key": "k"})

    def test_unicode(self):
        token = seal_dict("strong-master-key-here", {"api_key": "键", "api_secret": "秘"})
        out = open_dict("strong-master-key-here", token)
        assert out == {"api_key": "键", "api_secret": "秘"}


class TestLiveMode:
    def test_diagnosis_blocks_when_disabled(self, client: TestClient):
        resp = client.get("/api/v1/live/diagnosis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["authorized"] is False
        assert "deployment_flag" in data["blocking_gates"]

    def test_request_authorization_creates_approval(self, client: TestClient):
        resp = client.post("/api/v1/live/authorization/request", json={"account_id": "acc-1", "exchange": "binance"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["resource_type"] == "live_switch"
        assert data["resource_id"] == "acc-1"

    def test_live_preflight_rejected_without_flag(self, client: TestClient):
        approval_resp = client.post("/api/v1/live/authorization/request", json={"account_id": "paper-main"})
        approval = approval_resp.json()
        client.post(f"/api/v1/governance/approvals/{approval['approval_id']}/decide", json={"decision": "approved", "decided_by": "admin"})
        preflight = client.post("/api/v1/risk/preflight", json={
            "account_id": "paper-main",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.01",
            "price": "50000",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "live",
        })
        assert preflight.status_code == 200
        assert preflight.json()["decision"] == "rejected"
        assert "deployment_flag" in preflight.json()["reject_reason"]


class TestLiveRisk:
    def test_breaker_trips_after_threshold(self, client: TestClient):
        store = get_store()
        risk = store.live_risk_service
        for _ in range(30):
            risk.update_equity("paper-main", Decimal("100000"))
        risk.update_equity("paper-main", Decimal("85000"))
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


class TestBacktestEngine:
    def test_buy_and_hold_metrics(self):
        from app.services.backtest_engine import BacktestEngine
        from app.strategies.library.dual_ma import DualMaStrategy
        from app.strategies.signal import Signal, SignalType

        class BuyHold(DualMaStrategy):
            meta = DualMaStrategy.meta

            def on_bar(self, ctx, bar):
                return []

        bars = _bars(300, 100)
        engine = BacktestEngine(bars=bars, strategy_cls=BuyHold, params={}, initial_capital="100000")
        result = engine.run()
        assert result.status == "completed"
        assert result.total_trades == 0
        assert Decimal(result.net_profit) == Decimal("0")

    def test_slippage_and_fees_decrease_equity(self):
        from app.services.backtest_engine import BacktestEngine
        from app.strategies.library.dual_ma import DualMaStrategy
        from app.strategies.signal import Signal, SignalType

        class AlwaysBuy(DualMaStrategy):
            meta = DualMaStrategy.meta

            def on_bar(self, ctx, bar):
                if ctx.state.get("done"):
                    return []
                ctx.state["done"] = True
                return [Signal(type=SignalType.OPEN_LONG, symbol=self.meta.symbols[0], quantity=Decimal("1"))]

        bars = _bars(300, 100)
        engine_no_cost = BacktestEngine(bars=bars, strategy_cls=AlwaysBuy, params={}, initial_capital="100000", fee_model="none", slippage_model="none")
        engine_cost = BacktestEngine(bars=bars, strategy_cls=AlwaysBuy, params={}, initial_capital="100000", fee_model="simple", slippage_model="fixed_bps")
        no_cost = engine_no_cost.run()
        cost = engine_cost.run()
        assert Decimal(cost.final_equity) <= Decimal(no_cost.final_equity)

    def test_grid_search_optimize(self):
        from app.services.backtest_engine import BacktestEngine
        from app.strategies.library.dual_ma import DualMaStrategy

        bars = _bars(300, 100)
        result = BacktestEngine.optimize(
            strategy_cls=DualMaStrategy,
            base_params={},
            param_grid={"fast_period": [5, 10], "slow_period": [20, 30]},
            bars=bars,
            initial_capital="100000",
            max_runs=4,
        )
        assert result["runs"] == 4
        assert result["best_params"] is not None


class TestHistoricalData:
    def test_csv_import(self, client: TestClient):
        csv_text = "open_time,open,high,low,close,volume\n1700000000000,100,101,99,100.5,10\n1700000060000,100.5,102,100,101.5,12\n"
        resp = client.post("/api/v1/research/historical/import/csv", json={"symbol": "BTCUSDT", "period": "1m", "csv_text": csv_text})
        assert resp.status_code == 200
        data = resp.json()
        assert data["bars_imported"] == 2
        assert data["errors"] == 0

    def test_list_series(self, client: TestClient):
        resp = client.get("/api/v1/research/historical/series")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


def _bars(count: int, start: int):
    from app.strategies.signal import Bar
    out = []
    price = Decimal(str(start))
    for i in range(count):
        price += Decimal("0.1")
        out.append(Bar(
            symbol="BTCUSDT",
            open_time=1700000000000 + i * 60000,
            open=price,
            high=price + Decimal("0.1"),
            low=price - Decimal("0.1"),
            close=price + Decimal("0.05"),
            volume=Decimal("10"),
            close_time=1700000059000 + i * 60000,
        ))
    return out
