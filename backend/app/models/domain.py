from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.enums import (
    ApprovalResourceType,
    ApprovalStatus,
    AuditEventType,
    BacktestStatus,
    KillSwitchStatus,
    MarketType,
    OrderSide,
    OrderStatus,
    OrderType,
    ReconciliationStatus,
    ResolutionDecision,
    RiskDecision,
    TradeMode,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Order:
    def __init__(
        self,
        client_order_id: str,
        account_id: str,
        strategy_id: str,
        strategy_version: str,
        symbol: str,
        market_type: MarketType,
        side: OrderSide,
        order_type: OrderType,
        quantity: str,
        limit_price: str | None = None,
        mode: TradeMode = TradeMode.PAPER,
        risk_decision_id: str | None = None,
    ):
        self.client_order_id = client_order_id
        self.account_id = account_id
        self.strategy_id = strategy_id
        self.strategy_version = strategy_version
        self.symbol = symbol
        self.market_type = market_type
        self.side = side
        self.order_type = order_type
        self.quantity = quantity
        self.limit_price = limit_price
        self.mode = mode
        self.risk_decision_id = risk_decision_id
        self.status = OrderStatus.PENDING
        self.filled_quantity = "0.00000000"
        self.average_price: str | None = None
        self.reject_reason: str | None = None
        self.created_at = utcnow()
        self.updated_at = self.created_at


class RiskPreflightResult:
    def __init__(
        self,
        decision_id: str,
        decision: RiskDecision,
        account_id: str,
        symbol: str,
        side: OrderSide,
        quantity: str,
        strategy_id: str,
        strategy_version: str,
        reject_reason: str | None = None,
        remaining_risk_budget: str = "1000000.00",
        rules_checked: list[dict] | None = None,
        mode: TradeMode = TradeMode.PAPER,
        price: str | None = None,
        notional: str | None = None,
    ):
        self.decision_id = decision_id
        self.decision = decision
        self.account_id = account_id
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.strategy_id = strategy_id
        self.strategy_version = strategy_version
        self.reject_reason = reject_reason
        self.remaining_risk_budget = remaining_risk_budget
        self.rules_checked = rules_checked or []
        self.mode = mode
        # preflight 时的价格口径：用于下单时核验订单名义价值未被抬高（防 max_notional 绕过）
        self.price = price
        self.notional = notional
        # 决策单次消费：成功下单后记录消费该决策的订单 id，再次引用时拒绝
        self.consumed_by: str | None = None
        self.created_at = utcnow()


class FillRecord:
    def __init__(
        self,
        fill_id: str,
        client_order_id: str,
        account_id: str,
        symbol: str,
        side: OrderSide,
        fill_quantity: str,
        fill_price: str,
        trade_mode: TradeMode = TradeMode.PAPER,
    ):
        self.fill_id = fill_id
        self.client_order_id = client_order_id
        self.account_id = account_id
        self.symbol = symbol
        self.side = side
        self.fill_quantity = fill_quantity
        self.fill_price = fill_price
        self.trade_mode = trade_mode
        self.created_at = utcnow()


class ReconciliationLog:
    def __init__(
        self,
        reconciliation_id: str,
        account_id: str,
        status: ReconciliationStatus,
        details: str,
        summary: dict | None = None,
    ):
        self.reconciliation_id = reconciliation_id
        self.account_id = account_id
        self.status = status
        self.details = details
        self.summary = summary or {}
        self.created_at = utcnow()


class ResolutionRecord:
    def __init__(
        self,
        resolution_id: str,
        reconciliation_id: str,
        account_id: str,
        decision: ResolutionDecision,
        reason: str,
        actor: str,
        idempotency_key: str | None = None,
    ):
        self.resolution_id = resolution_id
        self.reconciliation_id = reconciliation_id
        self.account_id = account_id
        self.decision = decision
        self.reason = reason
        self.actor = actor
        self.idempotency_key = idempotency_key
        self.created_at = utcnow()


class PortfolioTarget:
    def __init__(
        self,
        target_id: str,
        account_id: str,
        strategy_id: str,
        strategy_version: str,
        symbol: str,
        target_quantity: str,
        current_quantity: str,
        target_weight: str | None = None,
        mode: TradeMode = TradeMode.PAPER,
        idempotency_key: str | None = None,
    ):
        self.target_id = target_id
        self.account_id = account_id
        self.strategy_id = strategy_id
        self.strategy_version = strategy_version
        self.symbol = symbol
        self.target_quantity = target_quantity
        self.current_quantity = current_quantity
        self.target_weight = target_weight
        self.delta = str((Decimal(target_quantity) - Decimal(current_quantity)).quantize(Decimal("0.00000001")))
        self.mode = mode
        self.idempotency_key = idempotency_key
        self.created_at = utcnow()
        self.updated_at = self.created_at


class Position:
    def __init__(
        self,
        position_id: str,
        account_id: str,
        symbol: str,
        market_type: MarketType,
        side: OrderSide,
        quantity: str,
        entry_price: str,
        current_price: str,
        unrealized_pnl: str = "0.00",
        realized_pnl: str = "0.00",
    ):
        self.position_id = position_id
        self.account_id = account_id
        self.symbol = symbol
        self.market_type = market_type
        self.side = side
        self.quantity = quantity
        self.entry_price = entry_price
        self.current_price = current_price
        self.unrealized_pnl = unrealized_pnl
        self.realized_pnl = realized_pnl
        self.created_at = utcnow()
        self.updated_at = self.created_at


class AuditEvent:
    def __init__(
        self,
        event_id: str,
        event_type: AuditEventType | str,
        actor: str,
        resource_type: str,
        resource_id: str,
        details: dict | None = None,
        ip_address: str | None = None,
        trace_id: str | None = None,
    ):
        self.event_id = event_id
        self.event_type = event_type
        self.actor = actor
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.details = details or {}
        self.ip_address = ip_address
        self.trace_id = trace_id
        self.created_at = utcnow()


class Strategy:
    def __init__(
        self,
        strategy_id: str,
        name: str,
        version: str,
        description: str,
        parameters: dict | None = None,
        status: str = "active",
        code_ref: str | None = None,
        owner: str | None = None,
        kind: str | None = None,
    ):
        self.strategy_id = strategy_id
        self.name = name
        self.version = version
        self.description = description
        self.parameters = parameters or {}
        self.status = status
        self.code_ref = code_ref
        self.owner = owner
        self.kind = kind
        self.created_at = utcnow()
        self.updated_at = self.created_at


class Symbol:
    def __init__(
        self,
        symbol: str,
        base_asset: str,
        quote_asset: str,
        market_type: MarketType,
        min_qty: str = "0.00001",
        max_qty: str = "1000.0",
        tick_size: str = "0.01",
        status: str = "trading",
    ):
        self.symbol = symbol
        self.base_asset = base_asset
        self.quote_asset = quote_asset
        self.market_type = market_type
        self.min_qty = min_qty
        self.max_qty = max_qty
        self.tick_size = tick_size
        self.status = status


class Approval:
    def __init__(
        self,
        approval_id: str,
        resource_type: ApprovalResourceType,
        resource_id: str,
        requested_by: str,
        title: str,
        details: str = "",
        ttl_seconds: int = 86400,
    ):
        self.approval_id = approval_id
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.requested_by = requested_by
        self.title = title
        self.details = details
        self.status = ApprovalStatus.PENDING
        self.decided_by: str | None = None
        self.reject_reason: str | None = None
        self.ttl_seconds = ttl_seconds
        self.created_at = utcnow()
        self.decided_at: datetime | None = None
        self.expires_at = utcnow().replace(second=0, microsecond=0) + timedelta(seconds=ttl_seconds)

    def is_expired(self) -> bool:
        return utcnow() > self.expires_at


class KillSwitchState:
    def __init__(self):
        self.status = KillSwitchStatus.INACTIVE
        self.triggered_by: str | None = None
        self.trigger_reason: str | None = None
        self.triggered_at: datetime | None = None
        self.recovered_by: str | None = None
        self.recovered_at: datetime | None = None


class Backtest:
    def __init__(
        self,
        backtest_id: str,
        strategy_id: str,
        strategy_version: str,
        parameters: dict | None,
        data_snapshot: str,
        fee_model: str,
        slippage_model: str,
        run_environment: str,
        initial_capital: str,
        account_id: str = "paper-main",
        mode: TradeMode = TradeMode.PAPER,
        idempotency_key: str | None = None,
    ):
        self.backtest_id = backtest_id
        self.account_id = account_id
        self.strategy_id = strategy_id
        self.strategy_version = strategy_version
        self.parameters = parameters or {}
        self.data_snapshot = data_snapshot
        self.fee_model = fee_model
        self.slippage_model = slippage_model
        self.run_environment = run_environment
        self.initial_capital = initial_capital
        self.mode = mode
        self.idempotency_key = idempotency_key
        self.code_ref: str | None = None
        self.status = BacktestStatus.RUNNING
        self.net_profit: str | None = None
        self.sharpe_ratio: str | None = None
        self.max_drawdown: str | None = None
        self.win_rate: str | None = None
        self.total_trades: int = 0
        self.created_at = utcnow()
        self.completed_at: datetime | None = None


class Ticker:
    def __init__(
        self,
        symbol: str,
        last_price: str,
        bid_price: str,
        ask_price: str,
        volume_24h: str,
        change_24h: str,
        high_24h: str,
        low_24h: str,
        source: str = "seeded-paper",
        event_time: datetime | None = None,
        ingest_time: datetime | None = None,
        sequence: int | None = None,
    ):
        self.symbol = symbol
        self.last_price = last_price
        self.bid_price = bid_price
        self.ask_price = ask_price
        self.volume_24h = volume_24h
        self.change_24h = change_24h
        self.high_24h = high_24h
        self.low_24h = low_24h
        self.source = source
        self.event_time = event_time or utcnow()
        self.ingest_time = ingest_time or utcnow()
        self.sequence = sequence


class StrategyRun:
    def __init__(
        self,
        run_id: str,
        strategy_id: str,
        strategy_version: str,
        account_id: str,
        mode: TradeMode,
        dry_run: bool,
        status: str,
        data_quality: dict,
        signals: list[dict],
        orders: list[dict] | None = None,
        reason: str | None = None,
    ):
        self.run_id = run_id
        self.strategy_id = strategy_id
        self.strategy_version = strategy_version
        self.account_id = account_id
        self.mode = mode
        self.dry_run = dry_run
        self.status = status
        self.data_quality = data_quality
        self.signals = signals
        self.orders = orders or []
        self.reason = reason
        self.created_at = utcnow()
        self.completed_at = self.created_at
