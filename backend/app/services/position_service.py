import uuid
from decimal import Decimal
from typing import Any

from app.core.errors import QuantError
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc
from app.models.domain import Position, utcnow
from app.models.enums import MarketType, OrderSide, TradeMode


class PositionService:
    def __init__(self, store: Any):
        self._store = store
        self._seed()

    def _seed(self):
        pos = Position(
            position_id="pos-btc-001",
            account_id="paper-main",
            symbol="BTCUSDT",
            market_type=MarketType.SPOT,
            side=OrderSide.BUY,
            quantity="0.50000000",
            entry_price="95000.00",
            current_price="100000.12",
            unrealized_pnl="2500.06",
            realized_pnl="150.00",
        )
        self._store.positions[pos.position_id] = pos

    def get_positions(self, account_id: str | None = None) -> list[Position]:
        positions = list(self._store.positions.values())
        if account_id:
            positions = [p for p in positions if p.account_id == account_id]
        return positions

    def available_to_offset(self, account_id: str, symbol: str, side: str) -> Decimal:
        """可冲减的反向持仓总量（只读，口径与 update_on_fill 完全一致）。

        SELL 单看同 account+symbol 的 BUY 持仓总量；BUY 单看 SELL 持仓总量。
        在 store 锁内读取，与 update_on_fill 的记账保持同一快照。
        """
        side_enum = OrderSide(side)
        opposite = OrderSide.BUY if side_enum == OrderSide.SELL else OrderSide.SELL
        with self._store.get_lock():
            return sum(
                (
                    Decimal(p.quantity)
                    for p in self._store.positions.values()
                    if p.account_id == account_id
                    and p.symbol == symbol
                    and p.side == opposite
                    and Decimal(p.quantity) > 0
                ),
                Decimal("0"),
            )

    def update_on_fill(
        self,
        account_id: str,
        symbol: str,
        side: str,
        fill_quantity: str,
        fill_price: str,
        trace_id: str | None = None,
    ) -> dict:
        """现货口径的成交记账。

        规则：
        - SELL 成交优先冲减同 symbol 的 BUY（多头）持仓；BUY 成交对称地
          优先冲减 SELL（空头）持仓（若存在）。
        - 跨多个反向持仓时按先进先出（FIFO）依次冲减，排序键为
          (created_at, position_id)，保证确定性。
        - 每笔冲减按持仓均价计已实现盈亏：冲减多头为
          (fill_price - entry) * offset_qty；冲减空头为
          (entry - fill_price) * offset_qty。
        - 冲减完仍有剩余量：保持现有行为（加仓或新建同方向持仓，
          entry_price 用成交价，加仓按加权平均更新 entry）。
        - 超卖（SELL 量超过可用 BUY 持仓总量）：明确拒绝，招
          INSUFFICIENT_POSITION/400，不再静默夹零。

        并发：本方法由调用方（order_execution_service）在 store 锁内/外
          保持原有调用方式，本实现不引入新的并发模型。
        """
        fill_qty = Decimal(fill_quantity)
        try:
            fill_prc = Decimal(fill_price)
        except Exception:
            raise QuantError("VALIDATION_ERROR", f"fill_price is not a valid decimal: {fill_price!r}", status_code=400)
        # 成交价必须为正：防止市价单等路径以 "0.00" 记账算出全额负 realized_pnl
        if not fill_prc.is_finite() or fill_prc <= 0:
            raise QuantError("VALIDATION_ERROR", f"fill_price must be positive and finite, got {fill_price!r}", status_code=400)
        side_enum = OrderSide(side)
        opposite = OrderSide.BUY if side_enum == OrderSide.SELL else OrderSide.SELL

        # 反向可冲减持仓，FIFO 排序（见 docstring）
        opposite_positions = sorted(
            (
                p
                for p in self._store.positions.values()
                if p.account_id == account_id
                and p.symbol == symbol
                and p.side == opposite
                and Decimal(p.quantity) > 0
            ),
            key=lambda p: (p.created_at, p.position_id),
        )
        available = sum((Decimal(p.quantity) for p in opposite_positions), Decimal("0"))

        # 超卖检查：现货不允许卖出超过持有多头的数量
        if side_enum == OrderSide.SELL and fill_qty > available:
            raise QuantError(
                "INSUFFICIENT_POSITION",
                f"Cannot sell {fill_qty} of {symbol} on account {account_id}: "
                f"only {available} available in long positions",
                status_code=400,
            )

        remaining = fill_qty
        realized_delta = Decimal("0")
        last_offset: Position | None = None

        for pos in opposite_positions:
            if remaining <= 0:
                break
            pos_qty = Decimal(pos.quantity)
            offset_qty = pos_qty if pos_qty < remaining else remaining
            entry = Decimal(pos.entry_price)
            if side_enum == OrderSide.SELL:
                pnl = (fill_prc - entry) * offset_qty
            else:
                pnl = (entry - fill_prc) * offset_qty

            new_qty = pos_qty - offset_qty
            pos.quantity = str(new_qty.quantize(Decimal("0.00000001")))
            pos.realized_pnl = str((Decimal(pos.realized_pnl) + pnl).quantize(Decimal("0.01")))
            pos.current_price = str(fill_prc.quantize(Decimal("0.01")))
            if new_qty <= 0:
                pos.unrealized_pnl = "0.00"
            else:
                upnl = (fill_prc - entry) * new_qty if opposite == OrderSide.BUY else (entry - fill_prc) * new_qty
                pos.unrealized_pnl = str(upnl.quantize(Decimal("0.01")))
            pos.updated_at = utcnow()

            realized_delta += pnl
            last_offset = pos
            remaining -= offset_qty

            event_bus.publish(DomainEvent(
                event_type=event_type("position", "updated"),
                event_id=new_event_id("pos"),
                event_time=now_utc(),
                version=1,
                actor=account_id,
                resource_type="position",
                resource_id=pos.position_id,
                payload={
                    "symbol": symbol,
                    "side": pos.side.value,
                    "quantity": pos.quantity,
                    "entry_price": pos.entry_price,
                    "realized_pnl": pos.realized_pnl,
                    "offset_quantity": str(offset_qty.quantize(Decimal("0.00000001"))),
                    "fill_price": str(fill_prc.quantize(Decimal("0.01"))),
                },
            ))

        primary: Position | None = None
        created = False
        if remaining > 0:
            # 冲减完仍有剩余量：保持现有行为（加仓或新建同方向持仓）
            for p in self._store.positions.values():
                if p.account_id == account_id and p.symbol == symbol and p.side == side_enum:
                    primary = p
                    break

            if not primary:
                pos_id = f"pos-{uuid.uuid4().hex[:12]}"
                primary = Position(
                    position_id=pos_id,
                    account_id=account_id,
                    symbol=symbol,
                    market_type=MarketType.SPOT,
                    side=side_enum,
                    quantity="0.00000000",
                    entry_price=fill_price,
                    current_price=fill_price,
                    unrealized_pnl="0.00",
                    realized_pnl="0.00",
                )
                self._store.positions[pos_id] = primary
                created = True

            old_qty = Decimal(primary.quantity)
            old_entry = Decimal(primary.entry_price)

            if side_enum == OrderSide.BUY:
                new_qty = old_qty + remaining
                new_entry = ((old_entry * old_qty) + (fill_prc * remaining)) / new_qty if new_qty > 0 else fill_prc
                primary.quantity = str(new_qty.quantize(Decimal("0.00000001")))
                primary.entry_price = str(new_entry.quantize(Decimal("0.01")))
            else:
                # SELL 同方向加仓分支：由于上方超卖检查，现货下此分支不可达，
                # 保留与原实现一致的对称逻辑以防未来语义扩展。
                new_qty = old_qty + remaining
                primary.quantity = str(new_qty.quantize(Decimal("0.00000001")))

            primary.current_price = str(fill_prc.quantize(Decimal("0.01")))
            primary.updated_at = utcnow()

            event_bus.publish(DomainEvent(
                event_type=event_type("position", "updated"),
                event_id=new_event_id("pos"),
                event_time=now_utc(),
                version=1,
                actor=account_id,
                resource_type="position",
                resource_id=primary.position_id,
                payload={
                    "symbol": symbol,
                    "side": side,
                    "quantity": primary.quantity,
                    "entry_price": primary.entry_price,
                    "realized_pnl": primary.realized_pnl,
                },
            ))

        report_target = primary or last_offset
        return {
            "position_id": report_target.position_id,
            "created": created,
            "quantity": report_target.quantity,
            "entry_price": report_target.entry_price,
            "realized_pnl": report_target.realized_pnl,
            "realized_pnl_delta": str(realized_delta.quantize(Decimal("0.01"))),
        }

    def mark_to_market(
        self,
        account_id: str,
        symbol: str,
        mark_price: str,
        mode: str = "paper",
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        _assert_paper_only(mode)
        mark = _parse_decimal(mark_price, "mark_price")

        if idempotency_key:
            with self._store.get_lock():
                for existing in self._store.mtm_logs:
                    if existing.get("idempotency_key") == idempotency_key:
                        return existing

        updated = []
        for pos in self._store.positions.values():
            if pos.account_id != account_id or pos.symbol != symbol:
                continue
            qty = Decimal(pos.quantity)
            entry = Decimal(pos.entry_price)
            if qty > 0:
                if pos.side == OrderSide.BUY:
                    upnl = (mark - entry) * qty
                else:
                    upnl = (entry - mark) * qty
            else:
                upnl = Decimal("0")
            pos.current_price = str(mark.quantize(Decimal("0.01")))
            pos.unrealized_pnl = str(upnl.quantize(Decimal("0.01")))
            pos.updated_at = utcnow()
            event_bus.publish(DomainEvent(
                event_type=event_type("position", "mtm_updated"),
                event_id=new_event_id("mtm"),
                event_time=now_utc(),
                version=1,
                actor=account_id,
                resource_type="position",
                resource_id=pos.position_id,
                payload={
                    "symbol": symbol,
                    "side": pos.side.value,
                    "quantity": pos.quantity,
                    "entry_price": pos.entry_price,
                    "mark_price": str(mark),
                    "unrealized_pnl": pos.unrealized_pnl,
                    "current_price": pos.current_price,
                },
            ))
            updated.append({
                "position_id": pos.position_id,
                "symbol": pos.symbol,
                "side": pos.side.value,
                "quantity": pos.quantity,
                "entry_price": pos.entry_price,
                "mark_price": str(mark.quantize(Decimal("0.01"))),
                "unrealized_pnl": pos.unrealized_pnl,
                "current_price": pos.current_price,
            })

        result = {
            "account_id": account_id,
            "symbol": symbol,
            "mark_price": str(mark.quantize(Decimal("0.01"))),
            "positions_updated": len(updated),
            "updates": updated,
            "idempotency_key": idempotency_key,
        }
        if idempotency_key:
            with self._store.get_lock():
                self._store.mtm_logs.append(result)
        return result


def _assert_paper_only(mode: str) -> None:
    try:
        m = TradeMode(mode)
    except ValueError:
        raise QuantError("VALIDATION_ERROR", f"Invalid mode: {mode!r}", status_code=400)
    if m != TradeMode.PAPER:
        raise QuantError("LIVE_TRADING_NOT_ALLOWED", "Only paper position mark-to-market is permitted", status_code=403)


def _parse_decimal(value: str, label: str) -> Decimal:
    if not isinstance(value, str) or not value.strip():
        raise QuantError("VALIDATION_ERROR", f"{label} must be a non-empty string", status_code=400)
    try:
        d = Decimal(value.strip())
    except Exception:
        raise QuantError("VALIDATION_ERROR", f"{label} is not a valid decimal: {value!r}", status_code=400)
    if not d.is_finite() or d < 0:
        raise QuantError("VALIDATION_ERROR", f"{label} must be non-negative and finite", status_code=400)
    return d