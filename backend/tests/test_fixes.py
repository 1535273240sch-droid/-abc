"""Regression tests for P0 fixes:

1. execute_via_adapter must be idempotent: repeated execution must not
   double-book fills or inflate positions (P0-1).
2. execute_via_adapter must reject terminal (cancelled/rejected) orders (P0-1).
3. Kill switch state must be persisted with the store and survive a restart
   (P0-2).
"""

from decimal import Decimal

from app.db.memory import InMemoryStore, get_store, reset_store
from app.models.enums import KillSwitchStatus


def _position_total_qty(store, account_id="paper-main", symbol="BTCUSDT") -> Decimal:
    total = Decimal("0")
    for pos in store.positions.values():
        if pos.account_id == account_id and pos.symbol == symbol:
            total += Decimal(pos.quantity)
    return total


def _fills_for(store, client_order_id):
    return [f for f in store.fills.values() if f.client_order_id == client_order_id]


def test_adapter_execute_idempotent_no_double_booking(client):
    d = client.post(
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
    ).json()
    assert d["decision"] == "approved"

    cid = "exec-adapt-rep"
    client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": cid,
            "account_id": "paper-main",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "99900.00",
            "mode": "paper",
            "risk_decision_id": d["decision_id"],
        },
    )

    store = get_store()
    r1 = client.post(f"/api/v1/execution/orders/{cid}/execute", json={})
    assert r1.status_code == 200
    fills_1 = _fills_for(store, cid)
    qty_1 = _position_total_qty(store)
    filled_1 = r1.json()["filled_quantity"]

    # 再次执行同一订单：不得新增成交记录、不得重复累加持仓
    r2 = client.post(f"/api/v1/execution/orders/{cid}/execute", json={})
    assert r2.status_code == 200
    fills_2 = _fills_for(store, cid)
    qty_2 = _position_total_qty(store)

    assert len(fills_2) == len(fills_1) == 1
    assert qty_2 == qty_1
    assert r2.json()["filled_quantity"] == filled_1


def test_adapter_execute_rejects_cancelled_order(client):
    d = client.post(
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
    ).json()
    assert d["decision"] == "approved"

    cid = "exec-adapt-cxl"
    client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": cid,
            "account_id": "paper-main",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "99900.00",
            "mode": "paper",
            "risk_decision_id": d["decision_id"],
        },
    )
    cxl = client.post(
        f"/api/v1/execution/orders/{cid}/cancel",
        json={"client_order_id": cid},
    )
    assert cxl.status_code == 200

    resp = client.post(f"/api/v1/execution/orders/{cid}/execute", json={})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_kill_switch_state_bound_to_store(client):
    store = get_store()
    resp = client.post(
        "/api/v1/governance/kill-switch/trigger",
        json={"triggered_by": "tester", "reason": "drill"},
    )
    assert resp.status_code == 200
    assert store.kill_switch_state is not None
    assert store.kill_switch_state.status == KillSwitchStatus.ACTIVE


def test_kill_switch_state_in_persisted_fields():
    assert "kill_switch_state" in InMemoryStore._persisted_fields


def test_kill_switch_survives_store_reload(monkeypatch, tmp_path, client):
    from app.core.config import settings

    state_path = tmp_path / "quant-store.pkl"
    monkeypatch.setattr(settings, "storage_enabled", True)
    monkeypatch.setattr(settings, "storage_backend", "pickle")
    monkeypatch.setattr(settings, "storage_path", str(state_path))

    store = get_store()
    resp = client.post(
        "/api/v1/governance/kill-switch/trigger",
        json={"triggered_by": "tester", "reason": "drill"},
    )
    assert resp.status_code == 200
    store.save()
    assert state_path.exists()

    # 模拟进程重启：清空注册表后用同一存储文件重建 store
    reset_store()
    store2 = get_store()
    assert store2.kill_switch_state is not None
    assert store2.kill_switch_state.status == KillSwitchStatus.ACTIVE
    assert store2.kill_switch_state.triggered_by == "tester"
