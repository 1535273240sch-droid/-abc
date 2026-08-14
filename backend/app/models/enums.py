from enum import Enum


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    RISK_REJECTED = "risk_rejected"
    REJECTED = "rejected"
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"


class MarketType(str, Enum):
    SPOT = "spot"
    FUTURE = "future"
    PERPETUAL = "perpetual"


class TradeMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class RiskDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class BacktestStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReconciliationStatus(str, Enum):
    CONSISTENT = "consistent"
    DISCREPANCY = "discrepancy"


class ResolutionDecision(str, Enum):
    ACKNOWLEDGED = "acknowledged"
    REJECTED = "rejected"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalResourceType(str, Enum):
    STRATEGY_PUBLISH = "strategy_publish"
    RISK_THRESHOLD_CHANGE = "risk_threshold_change"
    LIVE_SWITCH = "live_switch"
    KILL_SWITCH_RECOVERY = "kill_switch_recovery"


class KillSwitchStatus(str, Enum):
    INACTIVE = "inactive"
    ACTIVE = "active"


class AuditEventType(str, Enum):
    ORDER_CREATED = "order.created"
    ORDER_STATUS_CHANGED = "order.status_changed"
    ORDER_FILLED = "order.filled"
    RISK_PREFLIGHT = "risk.preflight"
    POSITION_UPDATED = "position.updated"
    POSITION_PNL_UPDATED = "position.pnl_updated"
    RECONCILIATION = "reconciliation.ran"
    SYSTEM_STARTUP = "system.startup"
    BACKTEST_CREATED = "backtest.created"
    BACKTEST_COMPLETED = "backtest.completed"
    APPROVAL_CREATED = "approval.created"
    APPROVAL_DECIDED = "approval.decided"
    KILL_SWITCH_TRIGGERED = "kill_switch.triggered"
    KILL_SWITCH_RECOVERED = "kill_switch.recovered"
    ADAPTER_CONNECTED = "adapter.connected"
    ADAPTER_DISCONNECTED = "adapter.disconnected"
    PORTFOLIO_TARGET_CREATED = "portfolio.target_created"
    POSITION_MTM_UPDATED = "position.mtm_updated"
    RECONCILIATION_RESOLVED = "reconciliation.resolved"