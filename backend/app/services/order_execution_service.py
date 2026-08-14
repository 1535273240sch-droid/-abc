import uuid
from decimal import Decimal
from typing import Any

from app.adapters.protocol import AdapterOrderStatus
from app.core.errors import QuantError
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc
from app.models.domain import FillRecord, utcnow
from app.models.enums import OrderSide, OrderStatus, TradeMode

_ADAPTER_STATUS_MAP = {
    AdapterOrderStatus.FILLED: OrderStatus.FILLED,
    AdapterOrderStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
    AdapterOrderStatus.NEW: OrderStatus.NEW,
    AdapterOrderStatus.CANCELLED: OrderStatus.CANCELLED,
    AdapterOrderStatus.REJECTED: OrderStatus.REJECTED,
}

_ALLOWED_TRANSITIONS = {
    OrderStatus.NEW: {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED},
    # 部分成交自迁移：一笔订单可能经历多次部分成交（PARTIALLY_FILLED -> PARTIALLY_FILLED），
    # 缺少该自迁移会导致第二次部分成交抛 INVALID_STATE_TRANSITION。
    OrderStatus.PARTIALLY_FILLED: {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED},
    OrderStatus.FILLED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.REJECTED: set(),
    OrderStatus.PENDING: set(),
    OrderStatus.RISK_REJECTED: set(),
}


class OrderExecutionService:
    def __init__(self, store: Any):
        self._store = store

    def _check_kill_switch(self):
        self._store.kill_switch_service.assert_not_active("execute order action")

    def fill(self, client_order_id: str, fill_quantity: str, fill_price: str) -> dict:
        self._check_kill_switch()
        with self._store.get_lock():
            order = self._store.orders.get(client_order_id)
            if not order:
                raise QuantError("NOT_FOUND", f"Order {client_order_id} not found", status_code=404)

            _validate_paper_mode(order.mode.value)
            _assert_live_allowed(self._store, order.mode.value)
            fill_qty = _parse_positive_decimal(fill_quantity, "fill_quantity")
            price = _parse_positive_decimal(fill_price, "fill_price")

            remaining = Decimal(order.quantity) - Decimal(order.filled_quantity)
            if fill_qty > remaining:
                raise QuantError(
                    "INVALID_FILL",
                    f"Fill quantity {fill_qty} exceeds remaining {remaining} for order {client_order_id}",
                    status_code=400,
                )

            # 持仓充足性预检（状态提交前）：超卖必须在订单状态迁移、写 FillRecord、
            # 发布事件之前拒绝，否则订单已变 FILLED 而持仓记账失败，造成账本撕裂。
            if order.side == OrderSide.SELL:
                available = self._store.position_service.available_to_offset(
                    account_id=order.account_id,
                    symbol=order.symbol,
                    side=order.side.value,
                )
                if fill_qty > available:
                    raise QuantError(
                        "INSUFFICIENT_POSITION",
                        f"Cannot sell {fill_qty} of {order.symbol} on account {order.account_id}: "
                        f"only {available} available in long positions",
                        status_code=400,
                    )

            if fill_qty < remaining:
                _transition(order, OrderStatus.PARTIALLY_FILLED)
            else:
                _transition(order, OrderStatus.FILLED)

            old_filled = Decimal(order.filled_quantity or "0")
            old_avg = Decimal(order.average_price or "0")
            new_filled = old_filled + fill_qty
            new_avg = ((old_avg * old_filled) + (price * fill_qty)) / new_filled if new_filled > 0 else price
            order.filled_quantity = str(new_filled.quantize(Decimal("0.00000001")))
            order.average_price = str(new_avg.quantize(Decimal("0.01")))
            order.updated_at = utcnow()

            fill_id = f"fill-{uuid.uuid4().hex[:12]}"
            fill_rec = FillRecord(
                fill_id=fill_id,
                client_order_id=client_order_id,
                account_id=order.account_id,
                symbol=order.symbol,
                side=order.side,
                fill_quantity=str(fill_qty.quantize(Decimal("0.00000001"))),
                fill_price=str(price.quantize(Decimal("0.01"))),
                trade_mode=order.mode,
            )
            self._store.fills[fill_id] = fill_rec

        event_bus.publish(DomainEvent(
            event_type=event_type("order", "filled"),
            event_id=new_event_id("fill"),
            event_time=now_utc(),
            version=1,
            actor=order.account_id,
            resource_type="order",
            resource_id=client_order_id,
            payload={
                "fill_id": fill_id,
                "fill_quantity": fill_rec.fill_quantity,
                "fill_price": fill_rec.fill_price,
                "status": order.status.value,
                "filled_quantity": order.filled_quantity,
            },
        ))

        position_updates = self._store.position_service.update_on_fill(
            account_id=order.account_id,
            symbol=order.symbol,
            side=order.side.value,
            fill_quantity=fill_rec.fill_quantity,
            fill_price=fill_rec.fill_price,
            trace_id=None,
        )

        return {
            "order": order,
            "fill": fill_rec,
            "position_updates": position_updates,
        }

    def cancel(self, client_order_id: str) -> Any:
        self._check_kill_switch()
        with self._store.get_lock():
            order = self._store.orders.get(client_order_id)
            if not order:
                raise QuantError("NOT_FOUND", f"Order {client_order_id} not found", status_code=404)
            _validate_paper_mode(order.mode.value)
            _assert_live_allowed(self._store, order.mode.value)
            _transition(order, OrderStatus.CANCELLED)
            order.updated_at = utcnow()

        event_bus.publish(DomainEvent(
            event_type=event_type("order", "cancelled"),
            event_id=new_event_id("cxl"),
            event_time=now_utc(),
            version=1,
            actor=order.account_id,
            resource_type="order",
            resource_id=client_order_id,
            payload={"status": order.status.value, "filled_quantity": order.filled_quantity},
        ))
        return order

    def reject(self, client_order_id: str, reason: str) -> Any:
        self._check_kill_switch()
        with self._store.get_lock():
            order = self._store.orders.get(client_order_id)
            if not order:
                raise QuantError("NOT_FOUND", f"Order {client_order_id} not found", status_code=404)
            _validate_paper_mode(order.mode.value)
            _assert_live_allowed(self._store, order.mode.value)
            _transition(order, OrderStatus.REJECTED)
            order.reject_reason = reason
            order.updated_at = utcnow()

        event_bus.publish(DomainEvent(
            event_type=event_type("order", "rejected"),
            event_id=new_event_id("rej"),
            event_time=now_utc(),
            version=1,
            actor=order.account_id,
            resource_type="order",
            resource_id=client_order_id,
            payload={"status": order.status.value, "reason": reason},
        ))
        return order

    def execute_via_adapter(self, client_order_id: str, trace_id: str | None = None) -> dict:
        self._check_kill_switch()

        with self._store.get_lock():
            order = self._store.orders.get(client_order_id)
            if not order:
                raise QuantError("NOT_FOUND", f"Order {client_order_id} not found", status_code=404)
            _validate_paper_mode(order.mode.value)
            _assert_live_allowed(self._store, order.mode.value)
            symbol = order.symbol
            side = order.side.value
            quantity = order.quantity
            price = order.limit_price

        result = self._store.adapter_service.place_paper_order(
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
        )

        new_status = _ADAPTER_STATUS_MAP.get(result.status, OrderStatus.NEW)
        reported_filled = Decimal(result.filled_quantity or "0.00000000")
        avg_price = result.average_price

        fill_rec = None
        position_updates = None

        with self._store.get_lock():
            order = self._store.orders.get(client_order_id)
            if not order:
                raise QuantError("NOT_FOUND", f"Order {client_order_id} not found", status_code=404)

            # 终态防护：已取消/已拒绝的订单不可再执行
            if order.status in (OrderStatus.CANCELLED, OrderStatus.REJECTED):
                raise QuantError(
                    "INVALID_STATE_TRANSITION",
                    f"Cannot execute order {client_order_id} in terminal status {order.status.value}",
                    status_code=400,
                )

            # 已全部成交：幂等返回，不再重复记账
            if order.status == OrderStatus.FILLED:
                return {
                    "order": order,
                    "fill": None,
                    "position_updates": None,
                    "adapter_result": {
                        "exchange": result.exchange,
                        "status": result.status.value,
                        "text": result.text,
                    },
                }

            # 增量成交记账：adapter 报告的是订单累计成交量，
            # 只对"新增"部分创建 fill 并更新持仓，避免重复执行导致仓位翻倍
            current_filled = Decimal(order.filled_quantity or "0")
            delta = reported_filled - current_filled
            if delta < 0:
                raise QuantError(
                    "INVALID_FILL",
                    f"Adapter reported filled {reported_filled} below current filled {current_filled} "
                    f"for order {client_order_id}",
                    status_code=400,
                )

            changed = False
            if delta > 0:
                # 持仓充足性预检（与 fill() 同口径）：在状态提交前拒绝超卖，
                # 避免订单已 FILLED/成交已落盘而持仓记账失败的账本撕裂
                if order.side == OrderSide.SELL:
                    available = self._store.position_service.available_to_offset(
                        account_id=order.account_id,
                        symbol=order.symbol,
                        side=order.side.value,
                    )
                    if delta > available:
                        raise QuantError(
                            "INSUFFICIENT_POSITION",
                            f"Cannot sell {delta} of {order.symbol} on account {order.account_id}: "
                            f"only {available} available in long positions",
                            status_code=400,
                        )

                # 价格回退：市价单（limit_price=None）经 paper adapter 会返回
                # average_price "0.00"/None；此时回退用订单 limit_price，
                # 两者都没有正值时拒绝记账，而不是以 0 价算出全额负盈亏
                effective_price = _positive_decimal_str(avg_price) or _positive_decimal_str(order.limit_price)
                if effective_price is None:
                    raise QuantError(
                        "INVALID_FILL",
                        f"No valid positive fill price for order {client_order_id} "
                        f"(adapter average_price={avg_price!r}, limit_price={order.limit_price!r})",
                        status_code=400,
                    )

                if order.status != new_status:
                    _transition(order, new_status)
                    order.updated_at = utcnow()
                order.average_price = effective_price
                order.filled_quantity = str(reported_filled.quantize(Decimal("0.00000001")))
                fill_id = f"fill-{uuid.uuid4().hex[:12]}"
                fill_rec = FillRecord(
                    fill_id=fill_id,
                    client_order_id=client_order_id,
                    account_id=order.account_id,
                    symbol=order.symbol,
                    side=order.side,
                    fill_quantity=str(delta.quantize(Decimal("0.00000001"))),
                    fill_price=effective_price,
                    trade_mode=order.mode,
                )
                self._store.fills[fill_id] = fill_rec
                changed = True
            elif order.status != new_status and new_status in (
                OrderStatus.CANCELLED,
                OrderStatus.REJECTED,
            ):
                # adapter 报告撤单/拒单（无新增成交）：推进状态机
                _transition(order, new_status)
                order.updated_at = utcnow()
                changed = True

        if fill_rec is not None:
            position_updates = self._store.position_service.update_on_fill(
                account_id=order.account_id,
                symbol=order.symbol,
                side=order.side.value,
                fill_quantity=fill_rec.fill_quantity,
                fill_price=fill_rec.fill_price,
                trace_id=trace_id,
            )

        event_bus.publish(DomainEvent(
            event_type=event_type("order", "filled"),
            event_id=new_event_id("fill"),
            event_time=now_utc(),
            version=1,
            actor=order.account_id,
            resource_type="order",
            resource_id=client_order_id,
            payload={
                "source": "adapter",
                "exchange": result.exchange,
                "fill_quantity": fill_rec.fill_quantity if fill_rec else str(reported_filled.quantize(Decimal("0.00000001"))),
                "status": order.status.value,
                "filled_quantity": order.filled_quantity,
            },
        ))

        return {
            "order": order,
            "fill": fill_rec,
            "position_updates": position_updates,
            "adapter_result": {"exchange": result.exchange, "status": result.status.value, "text": result.text},
        }


def _validate_paper_mode(mode: str) -> None:
    if mode != TradeMode.PAPER.value:
        raise QuantError(
            "LIVE_TRADING_NOT_ALLOWED",
            "Only paper orders can be executed in this environment",
            status_code=403,
        )


def _assert_live_allowed(store: Any, mode: str) -> None:
    if mode == TradeMode.PAPER.value:
        return
    if mode != TradeMode.PAPER.value:
        store.live_mode_service.assert_live_allowed()


def _parse_positive_decimal(value: str, label: str) -> Decimal:
    try:
        d = Decimal(value.strip())
    except Exception:
        raise QuantError("VALIDATION_ERROR", f"{label} is not a valid decimal: {value!r}", status_code=400)
    if not d.is_finite() or d <= 0:
        raise QuantError("VALIDATION_ERROR", f"{label} must be positive and finite", status_code=400)
    return d


def _positive_decimal_str(value: Any) -> str | None:
    """返回原值字符串（若其为正的有限十进制数），否则返回 None。"""
    if value is None:
        return None
    try:
        d = Decimal(str(value).strip())
    except Exception:
        return None
    if not d.is_finite() or d <= 0:
        return None
    return str(value)


def _transition(order, new_status: OrderStatus) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(order.status, set())
    if new_status not in allowed:
        raise QuantError(
            "INVALID_STATE_TRANSITION",
            f"Cannot transition order from {order.status.value} to {new_status.value}",
            status_code=400,
        )
    order.status = new_status