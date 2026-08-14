"""Regression tests for the three high-risk trading-logic fixes:

1. 订单状态机：PARTIALLY_FILLED 自迁移 —— 两次以上部分成交必须成功。
2. 风控决策：单次消费 + 名义价值核验 —— 同一决策第二次下单被拒，
   订单 limit_price 抬高导致 notional 超过 preflight 口径（容差 1.001）被拒。
3. 持仓记账：SELL 冲减多头并正确计算 realized_pnl；超卖明确拒绝；
   跨多个 BUY 持仓按 FIFO 冲减；BUY 对称冲减空头持仓。
"""

from decimal import Decimal

import pytest

from app.core.errors import QuantError
from app.db.memory import get_store, reset_store
from app.models.domain import Position
from app.models.enums import MarketType, OrderSide, RiskDecision


class _LegacyRiskDecision:
    """模拟升级前落盘的旧格式决策：没有 consumed_by/notional 属性。

    定义在模块级以便 pickle 序列化/反序列化。
    """

    def __init__(self, decision_id: str):
        self.decision_id = decision_id
        self.decision = RiskDecision.APPROVED
        self.account_id = "paper-main"
        self.symbol = "BTCUSDT"
        self.side = "buy"
        self.quantity = "0.01000000"
        self.strategy_id = "trend-btc"
        self.strategy_version = "1.0.0"
        self.reject_reason = None


def _preflight(client, **overrides):
    payload = {
        "account_id": "paper-main",
        "symbol": "BTCUSDT",
        "side": "buy",
        "quantity": "0.01000000",
        "price": "99900.00",
        "strategy_id": "trend-btc",
        "strategy_version": "1.0.0",
        "mode": "paper",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/risk/preflight", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["decision"] == "approved"
    return data


def _intent(client, decision_id, cid, **overrides):
    payload = {
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
        "risk_decision_id": decision_id,
    }
    payload.update(overrides)
    return client.post("/api/v1/orders/intents", json=payload)


def _fill(client, cid, quantity, price):
    return client.post(
        "/api/v1/execution/fills",
        json={"client_order_id": cid, "fill_quantity": quantity, "fill_price": price},
    )


# ── 修复 1：部分成交自迁移 ─────────────────────────────────────────────────────


def test_multiple_partial_fills_succeed(client):
    """同一订单连续两次部分成交后全额成交，不得抛 INVALID_STATE_TRANSITION。"""
    d = _preflight(client)
    r = _intent(client, d["decision_id"], "regress-multi-partial")
    assert r.status_code == 200

    f1 = _fill(client, "regress-multi-partial", "0.00300000", "99900.00")
    assert f1.status_code == 200
    assert f1.json()["status"] == "partially_filled"
    assert f1.json()["filled_quantity"] == "0.00300000"

    # 关键回归点：修复前第二次部分成交会抛 INVALID_STATE_TRANSITION
    f2 = _fill(client, "regress-multi-partial", "0.00300000", "99910.00")
    assert f2.status_code == 200, f2.text
    assert f2.json()["status"] == "partially_filled"
    assert f2.json()["filled_quantity"] == "0.00600000"

    f3 = _fill(client, "regress-multi-partial", "0.00400000", "99920.00")
    assert f3.status_code == 200
    assert f3.json()["status"] == "filled"
    assert f3.json()["filled_quantity"] == "0.01000000"


# ── 修复 2：风控决策单次消费 + 名义价值核验 ─────────────────────────────────────


def test_risk_decision_single_use_second_order_rejected(client):
    """同一 APPROVED 决策只能被一笔订单消费，第二次引用被拒。"""
    d = _preflight(client)

    r1 = _intent(client, d["decision_id"], "regress-consume-1")
    assert r1.status_code == 200

    r2 = _intent(client, d["decision_id"], "regress-consume-2")
    assert r2.status_code == 400
    assert r2.json()["error"]["code"] == "RISK_DECISION_ALREADY_CONSUMED"


def test_risk_decision_idempotent_retry_still_allowed(client):
    """幂等重试（同一 client_order_id）不应被单次消费规则误伤。"""
    d = _preflight(client)

    r1 = _intent(client, d["decision_id"], "regress-idem-retry")
    assert r1.status_code == 200
    r2 = _intent(client, d["decision_id"], "regress-idem-retry")
    assert r2.status_code == 200
    assert r2.json()["client_order_id"] == "regress-idem-retry"


def test_order_price_above_preflight_notional_rejected(client):
    """preflight 报低价、下单抬价绕过 max_notional 的路径必须被拒绝。"""
    # preflight notional = 0.01 * 99900.00 = 999.00
    d = _preflight(client)

    # 订单 notional = 0.01 * 120000.00 = 1200.00 > 999.00 * 1.001
    r = _intent(
        client,
        d["decision_id"],
        "regress-price-cap",
        limit_price="120000.00",
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "RISK_DECISION_PRICE_EXCEEDED"


def test_order_price_within_tolerance_allowed(client):
    """容差内（<= preflight notional * 1.001）的价格上浮应当放行。"""
    d = _preflight(client)
    # 99950.00 * 0.01 = 999.50 <= 999.00 * 1.001 = 999.999
    r = _intent(client, d["decision_id"], "regress-price-tol", limit_price="99950.00")
    assert r.status_code == 200, r.text


# ── 修复 3：SELL 冲减多头 / realized_pnl / 超卖拒绝 ─────────────────────────────


def test_sell_fill_reduces_long_and_books_realized_pnl(client):
    """SELL 成交冲减种子 BUY 持仓（entry 95000.00），realized_pnl 正确。"""
    d = _preflight(client, side="sell")
    r = _intent(client, d["decision_id"], "regress-sell-reduce", side="sell")
    assert r.status_code == 200, r.text

    # 以 99900.00 卖出 0.01：realized = (99900 - 95000) * 0.01 = 49.00
    f = _fill(client, "regress-sell-reduce", "0.01000000", "99900.00")
    assert f.status_code == 200, f.text
    updates = f.json()["position_updates"]
    assert updates["created"] is False
    assert updates["position_id"] == "pos-btc-001"
    assert updates["quantity"] == "0.49000000"
    assert updates["realized_pnl"] == "199.00"  # 种子 150.00 + 49.00
    assert updates["realized_pnl_delta"] == "49.00"

    store = get_store()
    pos = store.positions["pos-btc-001"]
    assert Decimal(pos.quantity) == Decimal("0.49000000")
    assert Decimal(pos.realized_pnl) == Decimal("199.00")
    # 不应错误地新建 SELL 空仓位
    assert not any(p.side == OrderSide.SELL for p in store.positions.values())


def test_oversell_rejected_not_silently_clamped(client):
    """SELL 量超过可用多头总量时必须报 INSUFFICIENT_POSITION，不再夹零；
    且拒绝必须发生在状态提交前：订单保持 NEW、无成交记录。"""
    d = _preflight(client, side="sell", quantity="0.60000000")
    r = _intent(
        client,
        d["decision_id"],
        "regress-oversell",
        side="sell",
        quantity="0.60000000",
    )
    assert r.status_code == 200, r.text

    f = _fill(client, "regress-oversell", "0.60000000", "99900.00")
    assert f.status_code == 400
    assert f.json()["error"]["code"] == "INSUFFICIENT_POSITION"

    store = get_store()
    # 种子持仓保持原状
    pos = store.positions["pos-btc-001"]
    assert Decimal(pos.quantity) == Decimal("0.50000000")
    assert Decimal(pos.realized_pnl) == Decimal("150.00")
    # 账本无撕裂：订单状态原样不动、未写 fill、未发事件副作用
    order = store.orders["regress-oversell"]
    assert order.status.value == "new"
    assert Decimal(order.filled_quantity) == Decimal("0")
    assert order.average_price is None
    assert not [fl for fl in store.fills.values() if fl.client_order_id == "regress-oversell"]


def test_sell_fifo_across_multiple_long_positions(client):
    """SELL 跨多个 BUY 持仓时按 (created_at, position_id) 先进先出冲减。"""
    store = get_store()
    p1 = Position(
        position_id="pos-fifo-1",
        account_id="paper-main",
        symbol="FIFUSDT",
        market_type=MarketType.SPOT,
        side=OrderSide.BUY,
        quantity="0.01000000",
        entry_price="100.00",
        current_price="100.00",
    )
    p2 = Position(
        position_id="pos-fifo-2",
        account_id="paper-main",
        symbol="FIFUSDT",
        market_type=MarketType.SPOT,
        side=OrderSide.BUY,
        quantity="0.02000000",
        entry_price="150.00",
        current_price="150.00",
    )
    store.positions[p1.position_id] = p1
    store.positions[p2.position_id] = p2

    d = _preflight(client, symbol="FIFUSDT", side="sell", quantity="0.01500000", price="120.00")
    r = _intent(
        client,
        d["decision_id"],
        "regress-fifo-sell",
        symbol="FIFUSDT",
        side="sell",
        quantity="0.01500000",
        limit_price="120.00",
    )
    assert r.status_code == 200, r.text

    f = _fill(client, "regress-fifo-sell", "0.01500000", "120.00")
    assert f.status_code == 200, f.text

    # p1 先被完全冲减：realized = (120-100)*0.01 = 0.20，数量归零
    assert Decimal(store.positions["pos-fifo-1"].quantity) == Decimal("0")
    assert Decimal(store.positions["pos-fifo-1"].realized_pnl) == Decimal("0.20")
    # p2 被冲减 0.005：realized = (120-150)*0.005 = -0.15，剩 0.015
    assert Decimal(store.positions["pos-fifo-2"].quantity) == Decimal("0.01500000")
    assert Decimal(store.positions["pos-fifo-2"].realized_pnl) == Decimal("-0.15")
    # 本次成交合计已实现盈亏 0.20 + (-0.15) = 0.05
    assert f.json()["position_updates"]["realized_pnl_delta"] == "0.05"


def test_buy_fill_offsets_short_position_first(client):
    """BUY 成交对称地优先冲减 SELL（空头）持仓，剩余量新建多头持仓。"""
    store = get_store()
    short = Position(
        position_id="pos-short-1",
        account_id="paper-main",
        symbol="SYMUSDT",
        market_type=MarketType.SPOT,
        side=OrderSide.SELL,
        quantity="0.01000000",
        entry_price="130.00",
        current_price="130.00",
    )
    store.positions[short.position_id] = short

    d = _preflight(client, symbol="SYMUSDT", quantity="0.01500000", price="120.00")
    r = _intent(
        client,
        d["decision_id"],
        "regress-buy-offset",
        symbol="SYMUSDT",
        quantity="0.01500000",
        limit_price="120.00",
    )
    assert r.status_code == 200, r.text

    f = _fill(client, "regress-buy-offset", "0.01500000", "120.00")
    assert f.status_code == 200, f.text

    # 空头被完全冲减：realized = (130-120)*0.01 = 0.10
    assert Decimal(store.positions["pos-short-1"].quantity) == Decimal("0")
    assert Decimal(store.positions["pos-short-1"].realized_pnl) == Decimal("0.10")

    # 剩余 0.005 新建 BUY 持仓，entry 用成交价
    longs = [p for p in store.positions.values() if p.symbol == "SYMUSDT" and p.side == OrderSide.BUY]
    assert len(longs) == 1
    assert Decimal(longs[0].quantity) == Decimal("0.00500000")
    assert Decimal(longs[0].entry_price) == Decimal("120.00")
    assert f.json()["position_updates"]["created"] is True


# ── 复审修复：问题 2（零价记账防线） ───────────────────────────────────────


def test_update_on_fill_rejects_non_positive_price(client):
    """update_on_fill 入口拒绝非正成交价，防止 0 价算出全额负盈亏。"""
    store = get_store()
    with pytest.raises(QuantError) as exc_info:
        store.position_service.update_on_fill("paper-main", "BTCUSDT", "buy", "0.01000000", "0.00")
    assert exc_info.value.code == "VALIDATION_ERROR"

    with pytest.raises(QuantError) as exc_info:
        store.position_service.update_on_fill("paper-main", "BTCUSDT", "buy", "0.01000000", "-5")
    assert exc_info.value.code == "VALIDATION_ERROR"


def test_market_order_without_price_rejected_on_execute(client):
    """市价单（limit_price=None）经 adapter 成交时无法取得正价，
    必须以 INVALID_FILL 拒绝记账，而不是以 0.00 落账；订单状态保持原样。

    注：cid "regress-mkt-1" 经 paper adapter 哈希确定性产生部分成交。
    """
    d = _preflight(client)
    r = _intent(
        client,
        d["decision_id"],
        "regress-mkt-1",
        order_type="market",
        limit_price=None,
    )
    assert r.status_code == 200, r.text

    resp = client.post("/api/v1/execution/orders/regress-mkt-1/execute", json={})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_FILL"

    store = get_store()
    order = store.orders["regress-mkt-1"]
    assert order.status.value == "new"
    assert Decimal(order.filled_quantity) == Decimal("0")
    assert not [fl for fl in store.fills.values() if fl.client_order_id == "regress-mkt-1"]


# ── 复审修复：问题 3（旧快照遗留决策清理） ─────────────────────────────────────


def test_legacy_risk_decisions_purged_on_load(monkeypatch, tmp_path, client):
    """快照加载后，缺少 consumed_by 属性的旧格式决策被一次性清除，
    新格式决策保留。"""
    from app.core.config import settings

    state_path = tmp_path / "quant-store.pkl"
    monkeypatch.setattr(settings, "storage_enabled", True)
    monkeypatch.setattr(settings, "storage_backend", "pickle")
    monkeypatch.setattr(settings, "storage_path", str(state_path))

    store = get_store()

    # 塞入一个旧格式假决策（无 consumed_by/notional 属性）
    legacy = _LegacyRiskDecision("legacy-decision-001")
    assert not hasattr(legacy, "consumed_by")
    store.risk_decisions["legacy-decision-001"] = legacy

    # 再产生一个新格式决策作对照
    fresh = _preflight(client)
    fresh_id = fresh["decision_id"]

    store.save()
    assert state_path.exists()

    # 模拟进程重启：触发快照加载路径
    reset_store()
    store2 = get_store()
    assert "legacy-decision-001" not in store2.risk_decisions
    assert fresh_id in store2.risk_decisions
    assert hasattr(store2.risk_decisions[fresh_id], "consumed_by")


# ── 复审修复：问题 4（preflight 拒绝零价） ────────────────────────────────────


def test_preflight_zero_price_rejected(client):
    """price=0 会产生 notional=0 的死决策，入口直接拒绝。"""
    resp = client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": "paper-main",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.01000000",
            "price": "0",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
