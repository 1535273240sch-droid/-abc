"""SQLAlchemy ORM models for all domain entities.

These models map the in-memory domain objects to relational tables,
enabling proper SQL queries, backups, and schema migrations via Alembic.

The ORM models are intentionally separate from the plain ``domain.py``
classes so that the service layer can continue to work with lightweight
in-memory objects while persistence is handled by this layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────── Orders ───────────────────

class OrderModel(Base):
    __tablename__ = "orders"

    client_order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    market_type: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[str] = mapped_column(String(64), nullable=False)
    limit_price: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    risk_decision_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    filled_quantity: Mapped[str] = mapped_column(String(64), nullable=False, default="0.00000000")
    average_price: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class FillRecordModel(Base):
    __tablename__ = "fill_records"

    fill_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String(64), ForeignKey("orders.client_order_id"), index=True, nullable=False)
    account_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    fill_quantity: Mapped[str] = mapped_column(String(64), nullable=False)
    fill_price: Mapped[str] = mapped_column(String(64), nullable=False)
    trade_mode: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)

    order: Mapped[OrderModel] = relationship("OrderModel", back_populates="fills")


OrderModel.fills = relationship("FillRecordModel", back_populates="order", cascade="all, delete-orphan")


# ─────────────────── Risk ───────────────────

class RiskDecisionModel(Base):
    __tablename__ = "risk_decisions"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    remaining_risk_budget: Mapped[str] = mapped_column(String(64), nullable=False, default="1000000.00")
    rules_checked: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    price: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notional: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consumed_by: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)


# ─────────────────── Positions ───────────────────

class PositionModel(Base):
    __tablename__ = "positions"

    position_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    market_type: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_price: Mapped[str] = mapped_column(String(64), nullable=False)
    current_price: Mapped[str] = mapped_column(String(64), nullable=False)
    unrealized_pnl: Mapped[str] = mapped_column(String(64), nullable=False, default="0.00")
    realized_pnl: Mapped[str] = mapped_column(String(64), nullable=False, default="0.00")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("account_id", "symbol", "side", name="uq_position_account_symbol_side"),
    )


# ─────────────────── Strategy ───────────────────

class StrategyModel(Base):
    __tablename__ = "strategies"

    strategy_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    code_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kind: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class StrategyRunModel(Base):
    __tablename__ = "strategy_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    account_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    data_quality: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    signals: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    orders: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)


# ─────────────────── Market Data ───────────────────

class SymbolModel(Base):
    __tablename__ = "symbols"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    base_asset: Mapped[str] = mapped_column(String(16), nullable=False)
    quote_asset: Mapped[str] = mapped_column(String(16), nullable=False)
    market_type: Mapped[str] = mapped_column(String(16), nullable=False)
    min_qty: Mapped[str] = mapped_column(String(32), nullable=False, default="0.00001")
    max_qty: Mapped[str] = mapped_column(String(32), nullable=False, default="1000.0")
    tick_size: Mapped[str] = mapped_column(String(32), nullable=False, default="0.01")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="trading", index=True)


class TickerModel(Base):
    __tablename__ = "tickers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    last_price: Mapped[str] = mapped_column(String(64), nullable=False)
    bid_price: Mapped[str] = mapped_column(String(64), nullable=False)
    ask_price: Mapped[str] = mapped_column(String(64), nullable=False)
    volume_24h: Mapped[str] = mapped_column(String(64), nullable=False)
    change_24h: Mapped[str] = mapped_column(String(64), nullable=False)
    high_24h: Mapped[str] = mapped_column(String(64), nullable=False)
    low_24h: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="seeded-paper")
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingest_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_ticker_symbol_time", "symbol", "ingest_time"),
    )


# ─────────────────── Audit ───────────────────

class AuditEventModel(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    actor: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    details: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)


# ─────────────────── Reconciliation ───────────────────

class ReconciliationLogModel(Base):
    __tablename__ = "reconciliation_logs"

    reconciliation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)


class ResolutionRecordModel(Base):
    __tablename__ = "resolution_records"

    resolution_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reconciliation_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    account_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)


# ─────────────────── Governance ───────────────────

class ApprovalModel(Base):
    __tablename__ = "approvals"

    approval_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=86400)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ─────────────────── Kill Switch ───────────────────

class KillSwitchModel(Base):
    __tablename__ = "kill_switch_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="inactive")
    triggered_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trigger_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recovered_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ─────────────────── Backtest ───────────────────

class BacktestModel(Base):
    __tablename__ = "backtests"

    backtest_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    parameters: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    data_snapshot: Mapped[str] = mapped_column(String(128), nullable=False)
    fee_model: Mapped[str] = mapped_column(String(32), nullable=False)
    slippage_model: Mapped[str] = mapped_column(String(32), nullable=False)
    run_environment: Mapped[str] = mapped_column(String(32), nullable=False)
    initial_capital: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    code_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running", index=True)
    net_profit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sharpe_ratio: Mapped[str | None] = mapped_column(String(64), nullable=True)
    max_drawdown: Mapped[str | None] = mapped_column(String(64), nullable=True)
    win_rate: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ─────────────────── Portfolio ───────────────────

class PortfolioTargetModel(Base):
    __tablename__ = "portfolio_targets"

    target_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    target_quantity: Mapped[str] = mapped_column(String(64), nullable=False)
    current_quantity: Mapped[str] = mapped_column(String(64), nullable=False)
    target_weight: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delta: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


# ─────────────────── Agent Tasks ───────────────────

class AgentTaskModel(Base):
    __tablename__ = "agent_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    input_payload: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    output_payload: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ─────────────────── Alerts ───────────────────

class AlertModel(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    context: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ─────────────────── Exchange Connections ───────────────────

class ExchangeConnectionModel(Base):
    __tablename__ = "exchange_connections"

    connection_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="disconnected", index=True)
    config: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


# ─────────────────── AI Model Providers ───────────────────

class AIProviderModel(Base):
    __tablename__ = "ai_model_providers"

    provider_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    config: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="inactive", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


# ─────────────────── MTM Logs ───────────────────

class MTMLogModel(Base):
    __tablename__ = "mtm_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    position_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    mark_price: Mapped[str] = mapped_column(String(64), nullable=False)
    unrealized_pnl: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)


# ─────────────────── Historical Klines ───────────────────

class HistoricalKlineModel(Base):
    __tablename__ = "historical_klines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    open_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    open: Mapped[str] = mapped_column(String(64), nullable=False)
    high: Mapped[str] = mapped_column(String(64), nullable=False)
    low: Mapped[str] = mapped_column(String(64), nullable=False)
    close: Mapped[str] = mapped_column(String(64), nullable=False)
    volume: Mapped[str] = mapped_column(String(64), nullable=False)
    close_time: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("symbol", "period", "open_time", name="uq_kline_symbol_period_time"),
        Index("ix_kline_symbol_period_time", "symbol", "period", "open_time"),
    )
