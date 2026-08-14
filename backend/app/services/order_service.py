import uuid
from decimal import Decimal, DecimalException, InvalidOperation
from typing import Any

from app.core.errors import QuantError
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc
from app.models.domain import Order
from app.models.enums import MarketType, OrderSide, OrderStatus, OrderType, RiskDecision, TradeMode

# 订单名义价值相对 preflight notional 的最大容差倍数。
# 取值 1.001（0.1% 容差）：仅容纳价格精度/量化误差，任何实质性的价格抬高
# （例如 preflight 报低价、下单提价以绕过 max_notional）都会被拒绝。
_NOTIONAL_TOLERANCE = Decimal("1.001")


class OrderService:
    def __init__(self, store: Any):
        self._store = store

    def create_intent(
        self,
        client_order_id: str,
        account_id: str,
        strategy_id: str,
        strategy_version: str,
        symbol: str,
        market_type: str,
        side: str,
        order_type: str,
        quantity: str,
        limit_price: str | None,
        mode: str,
        risk_decision_id: str,
    ) -> Order:
        _assert_paper_only(mode)
        _assert_live_allowed(self._store, mode)
        self._store.kill_switch_service.assert_not_active("create order intent")

        with self._store.get_lock():
            if client_order_id in self._store.orders:
                existing = self._store.orders[client_order_id]
                _check_idempotent_conflict(
                    existing, account_id, strategy_id, strategy_version,
                    symbol, market_type, side, order_type, quantity, limit_price, mode, risk_decision_id,
                )
                return existing

            decision = self._store.risk_decisions.get(risk_decision_id)
            if not decision:
                raise QuantError(
                    "INVALID_RISK_DECISION",
                    f"Risk decision {risk_decision_id} not found",
                    status_code=400,
                )

            if decision.decision != RiskDecision.APPROVED:
                raise QuantError(
                    "RISK_REJECTED",
                    f"Risk decision {risk_decision_id} was not approved: {decision.reject_reason}",
                    status_code=400,
                )

            # 决策单次消费：一个 APPROVED 决策只能被一笔订单使用。
            # 幂等重试（同一 client_order_id）在上方已提前返回，这里拒绝其他订单复用。
            consumed_by = getattr(decision, "consumed_by", None)
            if consumed_by and consumed_by != client_order_id:
                raise QuantError(
                    "RISK_DECISION_ALREADY_CONSUMED",
                    f"Risk decision {risk_decision_id} was already consumed by order {consumed_by}",
                    status_code=400,
                )

            _check_decision_match(
                decision, account_id, symbol, side, quantity,
                strategy_id, strategy_version, mode, limit_price,
            )

            order = Order(
                client_order_id=client_order_id,
                account_id=account_id,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                symbol=symbol,
                market_type=MarketType(market_type),
                side=OrderSide(side),
                order_type=OrderType(order_type),
                quantity=quantity,
                limit_price=limit_price,
                mode=TradeMode(mode),
                risk_decision_id=risk_decision_id,
            )
            order.status = OrderStatus.NEW

            self._store.orders[client_order_id] = order
            # 消费决策：在同一把锁内标记，避免并发下同一决策被两笔订单消费
            decision.consumed_by = client_order_id

        event_bus.publish(DomainEvent(
            event_type=event_type("order", "intent_created"),
            event_id=new_event_id("ord"),
            event_time=now_utc(),
            version=1,
            actor=account_id,
            resource_type="order",
            resource_id=order.client_order_id,
            payload={
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "status": order.status.value,
                "mode": order.mode.value,
                "risk_decision_id": order.risk_decision_id,
            },
        ))

        return order

    def get_orders(self, account_id: str | None = None) -> list[Order]:
        orders = list(self._store.orders.values())
        if account_id:
            orders = [o for o in orders if o.account_id == account_id]
        return sorted(orders, key=lambda o: o.created_at, reverse=True)

    def get_order(self, client_order_id: str) -> Order | None:
        return self._store.orders.get(client_order_id)


def _assert_paper_only(mode: str) -> None:
    try:
        m = TradeMode(mode)
    except ValueError:
        raise QuantError("VALIDATION_ERROR", f"Invalid trading mode: {mode!r}", status_code=400)
    if m != TradeMode.PAPER:
        raise QuantError(
            "LIVE_TRADING_NOT_ALLOWED",
            "Only paper trading is permitted in this environment",
            status_code=403,
        )


def _assert_live_allowed(store: Any, mode: str) -> None:
    """Gate live order creation through the three-way live-mode check.

    Kept as a separate function so the existing paper-only fast-path
    (no extra lookups) stays cheap, and the live path only runs when
    someone actually requests live mode.
    """
    if mode == TradeMode.PAPER.value:
        return
    try:
        m = TradeMode(mode)
    except ValueError:
        raise QuantError("VALIDATION_ERROR", f"Invalid trading mode: {mode!r}", status_code=400)
    if m != TradeMode.PAPER:
        store.live_mode_service.assert_live_allowed()


def _check_decision_match(decision, account_id, symbol, side, quantity, strategy_id, strategy_version, mode, limit_price=None):
    if decision.account_id != account_id:
        raise QuantError("RISK_DECISION_MISMATCH", "Risk decision account_id does not match order", status_code=400)
    if decision.symbol != symbol:
        raise QuantError("RISK_DECISION_MISMATCH", "Risk decision symbol does not match order", status_code=400)
    if decision.side != side:
        raise QuantError("RISK_DECISION_MISMATCH", "Risk decision side does not match order", status_code=400)
    if decision.quantity != quantity:
        raise QuantError("RISK_DECISION_MISMATCH", "Risk decision quantity does not match order", status_code=400)
    if decision.strategy_id != strategy_id:
        raise QuantError("RISK_DECISION_MISMATCH", "Risk decision strategy_id does not match order", status_code=400)
    if decision.strategy_version != strategy_version:
        raise QuantError("RISK_DECISION_MISMATCH", "Risk decision strategy_version does not match order", status_code=400)
    if decision.mode != TradeMode(mode):
        raise QuantError(
            "RISK_DECISION_MISMATCH",
            f"Risk decision mode ({decision.mode.value}) does not match order mode ({mode})",
            status_code=400,
        )

    # 价格/名义价值核验：订单 notional = limit_price * quantity 不得超过
    # preflight 时计算的 notional（允许 _NOTIONAL_TOLERANCE = 1.001 倍容差）。
    # 没有它，调用方可以在 preflight 自报低价通过 max_notional，
    # 再以高价 limit_price 下单绕过风控。
    # 边界声明：市价单（limit_price=None）创建时不参与 notional 核验，
    # 其价格防线在 fill 阶段以实际成交价记账（见 position_service.update_on_fill
    # 的 fill_price 正值校验与 execute_via_adapter 的价格回退逻辑）。
    if limit_price is not None and getattr(decision, "notional", None):
        try:
            price_d = Decimal(str(limit_price).strip())
            qty_d = Decimal(str(quantity).strip())
        except (DecimalException, InvalidOperation):
            raise QuantError(
                "VALIDATION_ERROR",
                f"limit_price/quantity must be valid decimals: {limit_price!r}/{quantity!r}",
                status_code=400,
            )
        if not price_d.is_finite() or price_d < 0:
            raise QuantError(
                "VALIDATION_ERROR",
                f"limit_price must be non-negative and finite, got {limit_price!r}",
                status_code=400,
            )
        order_notional = price_d * qty_d
        approved_notional = Decimal(decision.notional)
        if order_notional > approved_notional * _NOTIONAL_TOLERANCE:
            raise QuantError(
                "RISK_DECISION_PRICE_EXCEEDED",
                f"Order notional {order_notional} exceeds approved preflight notional "
                f"{approved_notional} (tolerance {_NOTIONAL_TOLERANCE}) for risk decision {decision.decision_id}",
                status_code=400,
            )


def _check_idempotent_conflict(
    existing, account_id, strategy_id, strategy_version,
    symbol, market_type, side, order_type, quantity, limit_price, mode, risk_decision_id,
):
    conflict_fields = {}
    if existing.account_id != account_id:
        conflict_fields["account_id"] = (existing.account_id, account_id)
    if existing.strategy_id != strategy_id:
        conflict_fields["strategy_id"] = (existing.strategy_id, strategy_id)
    if existing.strategy_version != strategy_version:
        conflict_fields["strategy_version"] = (existing.strategy_version, strategy_version)
    if existing.symbol != symbol:
        conflict_fields["symbol"] = (existing.symbol, symbol)
    if existing.market_type.value != market_type:
        conflict_fields["market_type"] = (existing.market_type.value, market_type)
    if existing.side.value != side:
        conflict_fields["side"] = (existing.side.value, side)
    if existing.order_type.value != order_type:
        conflict_fields["order_type"] = (existing.order_type.value, order_type)
    if existing.quantity != quantity:
        conflict_fields["quantity"] = (existing.quantity, quantity)
    if existing.limit_price != limit_price:
        conflict_fields["limit_price"] = (existing.limit_price, limit_price)
    if existing.mode.value != mode:
        conflict_fields["mode"] = (existing.mode.value, mode)
    if existing.risk_decision_id != risk_decision_id:
        conflict_fields["risk_decision_id"] = (existing.risk_decision_id, risk_decision_id)

    if conflict_fields:
        raise QuantError(
            "IDEMPOTENCY_CONFLICT",
            f"client_order_id {existing.client_order_id} already exists with different fields",
            status_code=409,
            details={"conflicts": {k: {"existing": v[0], "requested": v[1]} for k, v in conflict_fields.items()}},
        )