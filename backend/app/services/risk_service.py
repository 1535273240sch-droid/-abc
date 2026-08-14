import uuid
from decimal import Decimal, DecimalException, InvalidOperation
from datetime import datetime, timezone
from typing import Any

from app.core.errors import QuantError
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc
from app.models.domain import RiskPreflightResult
from app.models.enums import RiskDecision, TradeMode


def _parse_decimal(value: str, label: str) -> Decimal:
    if not isinstance(value, str) or not value.strip():
        raise QuantError("VALIDATION_ERROR", f"{label} must be a non-empty string", status_code=400)
    try:
        d = Decimal(value.strip())
    except (DecimalException, InvalidOperation):
        raise QuantError(
            "VALIDATION_ERROR",
            f"{label} is not a valid decimal number: {value!r}",
            status_code=400,
        )
    if not d.is_finite():
        raise QuantError(
            "VALIDATION_ERROR",
            f"{label} must be a finite number, got {value!r}",
            status_code=400,
        )
    if d < 0:
        raise QuantError("VALIDATION_ERROR", f"{label} must be non-negative, got {value!r}", status_code=400)
    return d


class RiskService:
    def __init__(self, store: Any):
        self._store = store

    def preflight(
        self,
        account_id: str,
        symbol: str,
        side: str,
        quantity: str,
        price: str,
        strategy_id: str,
        strategy_version: str,
        mode: str = "paper",
    ) -> RiskPreflightResult:
        try:
            trade_mode = TradeMode(mode)
        except ValueError:
            raise QuantError("VALIDATION_ERROR", f"Invalid trading mode: {mode!r}", status_code=400)

        if trade_mode == TradeMode.LIVE:
            # 三重门禁：部署开关 + 治理审批 + 交易所凭据（见 LiveModeService）。
            # 未全部满足时保持 API 兼容：返回 200 + rejected decision，而不是抛 403。
            try:
                self._store.live_mode_service.assert_live_allowed(account_id=account_id)
            except QuantError as exc:
                return RiskPreflightResult(
                    decision_id=str(uuid.uuid4()),
                    decision=RiskDecision.REJECTED,
                    account_id=account_id,
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                    reject_reason=exc.message,
                    mode=trade_mode,
                    price=str(_parse_decimal(price, "price")),
                    notional=str(_parse_decimal(quantity, "quantity") * _parse_decimal(price, "price")),
                )

        qty = _parse_decimal(quantity, "quantity")
        price_d = _parse_decimal(price, "price")
        # price=0 会产生 notional=0 的死决策：之后任何正价限价单必被
        # PRICE_EXCEEDED 拒绝，因此在入口直接拒绝非正价格
        if price_d <= 0:
            raise QuantError("VALIDATION_ERROR", f"price must be positive, got {price!r}", status_code=400)
        notional = qty * price_d

        rules_checked = []
        rejected = False
        reject_reason = None

        limit = Decimal("1000000")
        if notional > limit:
            rules_checked.append({"rule": "max_notional", "passed": False, "limit": str(limit), "value": str(notional)})
            rejected = True
            reject_reason = f"Notional value {notional} exceeds maximum allowed ({limit})"
        else:
            rules_checked.append({"rule": "max_notional", "passed": True, "limit": str(limit), "value": str(notional)})

        if qty <= 0:
            rules_checked.append({"rule": "positive_quantity", "passed": False})
            rejected = True
            reject_reason = "Quantity must be positive"
        else:
            rules_checked.append({"rule": "positive_quantity", "passed": True})

        min_qty = Decimal("0.00001")
        if qty < min_qty and not rejected:
            rules_checked.append({"rule": "min_quantity", "passed": False, "limit": str(min_qty), "value": str(qty)})
            rejected = True
            reject_reason = f"Quantity {qty} below minimum {min_qty}"
        else:
            rules_checked.append({"rule": "min_quantity", "passed": True, "limit": str(min_qty), "value": str(qty)})

        # 实盘专属增强规则：最大持仓集中度 + 回撤熔断（仅 live 模式）
        if trade_mode == TradeMode.LIVE:
            for live_rule in self._store.live_risk_service.check_order(
                account_id=account_id, symbol=symbol, side=side,
                quantity=quantity, price=price,
            ):
                rules_checked.append(live_rule)
                if live_rule.get("passed") is False:
                    rejected = True
                    reject_reason = live_rule.get("detail") or f"live risk rule {live_rule.get('rule')} failed"

        result = RiskPreflightResult(
            decision_id=str(uuid.uuid4()),
            decision=RiskDecision.REJECTED if rejected else RiskDecision.APPROVED,
            account_id=account_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            reject_reason=reject_reason,
            rules_checked=rules_checked,
            mode=trade_mode,
            # 记录 preflight 时的价格口径（price 与 notional = qty * price），
            # 供下单时核验订单 limit_price 未被抬高，防止 max_notional 规则被绕过。
            price=str(price_d),
            notional=str(notional),
        )

        with self._store.get_lock():
            self._store.risk_decisions[result.decision_id] = result

        event_bus.publish(DomainEvent(
            event_type=event_type("risk", "preflight"),
            event_id=new_event_id("risk"),
            event_time=now_utc(),
            version=1,
            actor=account_id,
            resource_type="risk_decision",
            resource_id=result.decision_id,
            payload={
                "decision": result.decision.value,
                "symbol": result.symbol,
                "side": result.side,
                "quantity": result.quantity,
                "mode": result.mode.value,
            },
        ))

        return result

    def get_decision(self, decision_id: str) -> RiskPreflightResult | None:
        return self._store.risk_decisions.get(decision_id)

    def rules(self) -> list[dict]:
        quality = self._store.market_service.quality()
        now = datetime.now(timezone.utc).isoformat()
        return [
            {"id": "max_notional", "name": "最大名义敞口", "scope": "order", "detail": "≤ 1,000,000", "result": "passed", "checked_at": now},
            {"id": "positive_quantity", "name": "正数量校验", "scope": "order", "detail": "quantity > 0", "result": "passed", "checked_at": now},
            {"id": "min_quantity", "name": "最小下单数量", "scope": "symbol", "detail": "按 Symbol min_qty", "result": "passed", "checked_at": now},
            {"id": "market_quality", "name": "行情质量门", "scope": "market_data", "detail": quality["status"], "result": "passed" if quality["usable"] and quality["status"] == "healthy" else "warning", "checked_at": quality["checked_at"]},
        ]

    def circuit_breakers(self) -> list[dict]:
        kill_switch = self._store.kill_switch_service.get_state()
        quality = self._store.market_service.quality()
        return [
            {"id": "kill_switch", "name": "全系统 Kill Switch", "target": "all execution", "trigger_condition": "人工触发或严重异常", "action": "阻断所有订单", "status": "已触发" if kill_switch.status.value == "active" else "正常"},
            {"id": "market_quality", "name": "行情质量保护", "target": "strategy runtime", "trigger_condition": "行情不可用或陈旧", "action": "阻断策略信号", "status": "已触发" if quality["status"] != "healthy" else "正常"},
            {"id": "public_feed", "name": "公网行情出口保护", "target": "public market feed", "trigger_condition": "刷新失败", "action": "回退 Paper 快照并告警", "status": "已触发" if quality.get("issues") else "正常"},
        ]
