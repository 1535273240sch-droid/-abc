"""Initial schema: all enterprise tables.

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00

This migration creates the full relational schema that replaces the
Pickle-blob persistence used in the prototype phase.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Orders ---
    op.create_table(
        "orders",
        sa.Column("client_order_id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False, index=True),
        sa.Column("strategy_id", sa.String(64), nullable=False, index=True),
        sa.Column("strategy_version", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False, index=True),
        sa.Column("market_type", sa.String(16), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("order_type", sa.String(16), nullable=False),
        sa.Column("quantity", sa.String(64), nullable=False),
        sa.Column("limit_price", sa.String(64), nullable=True),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("risk_decision_id", sa.String(64), nullable=True, index=True),
        sa.Column("status", sa.String(24), nullable=False, default="pending", index=True),
        sa.Column("filled_quantity", sa.String(64), nullable=False, default="0.00000000"),
        sa.Column("average_price", sa.String(64), nullable=True),
        sa.Column("reject_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- Fill Records ---
    op.create_table(
        "fill_records",
        sa.Column("fill_id", sa.String(64), primary_key=True),
        sa.Column("client_order_id", sa.String(64), sa.ForeignKey("orders.client_order_id"), nullable=False, index=True),
        sa.Column("account_id", sa.String(64), nullable=False, index=True),
        sa.Column("symbol", sa.String(32), nullable=False, index=True),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("fill_quantity", sa.String(64), nullable=False),
        sa.Column("fill_price", sa.String(64), nullable=False),
        sa.Column("trade_mode", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )

    # --- Risk Decisions ---
    op.create_table(
        "risk_decisions",
        sa.Column("decision_id", sa.String(64), primary_key=True),
        sa.Column("decision", sa.String(16), nullable=False, index=True),
        sa.Column("account_id", sa.String(64), nullable=False, index=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", sa.String(64), nullable=False),
        sa.Column("strategy_id", sa.String(64), nullable=False),
        sa.Column("strategy_version", sa.String(32), nullable=False),
        sa.Column("reject_reason", sa.Text, nullable=True),
        sa.Column("remaining_risk_budget", sa.String(64), nullable=False, default="1000000.00"),
        sa.Column("rules_checked", postgresql.JSONB, nullable=False, default=list),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("price", sa.String(64), nullable=True),
        sa.Column("notional", sa.String(64), nullable=True),
        sa.Column("consumed_by", sa.String(64), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )

    # --- Positions ---
    op.create_table(
        "positions",
        sa.Column("position_id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False, index=True),
        sa.Column("symbol", sa.String(32), nullable=False, index=True),
        sa.Column("market_type", sa.String(16), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", sa.String(64), nullable=False),
        sa.Column("entry_price", sa.String(64), nullable=False),
        sa.Column("current_price", sa.String(64), nullable=False),
        sa.Column("unrealized_pnl", sa.String(64), nullable=False, default="0.00"),
        sa.Column("realized_pnl", sa.String(64), nullable=False, default="0.00"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "symbol", "side", name="uq_position_account_symbol_side"),
    )

    # --- Strategies ---
    op.create_table(
        "strategies",
        sa.Column("strategy_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("parameters", postgresql.JSONB, nullable=False, default=dict),
        sa.Column("status", sa.String(16), nullable=False, default="active", index=True),
        sa.Column("code_ref", sa.String(256), nullable=True),
        sa.Column("owner", sa.String(64), nullable=True),
        sa.Column("kind", sa.String(32), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- Strategy Runs ---
    op.create_table(
        "strategy_runs",
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column("strategy_id", sa.String(64), nullable=False, index=True),
        sa.Column("strategy_version", sa.String(32), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False, index=True),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("dry_run", sa.Boolean, nullable=False),
        sa.Column("status", sa.String(24), nullable=False, index=True),
        sa.Column("data_quality", postgresql.JSONB, nullable=False, default=dict),
        sa.Column("signals", postgresql.JSONB, nullable=False, default=list),
        sa.Column("orders", postgresql.JSONB, nullable=False, default=list),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- Symbols ---
    op.create_table(
        "symbols",
        sa.Column("symbol", sa.String(32), primary_key=True),
        sa.Column("base_asset", sa.String(16), nullable=False),
        sa.Column("quote_asset", sa.String(16), nullable=False),
        sa.Column("market_type", sa.String(16), nullable=False),
        sa.Column("min_qty", sa.String(32), nullable=False, default="0.00001"),
        sa.Column("max_qty", sa.String(32), nullable=False, default="1000.0"),
        sa.Column("tick_size", sa.String(32), nullable=False, default="0.01"),
        sa.Column("status", sa.String(16), nullable=False, default="trading", index=True),
    )

    # --- Tickers (time-series) ---
    op.create_table(
        "tickers",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(32), nullable=False, index=True),
        sa.Column("last_price", sa.String(64), nullable=False),
        sa.Column("bid_price", sa.String(64), nullable=False),
        sa.Column("ask_price", sa.String(64), nullable=False),
        sa.Column("volume_24h", sa.String(64), nullable=False),
        sa.Column("change_24h", sa.String(64), nullable=False),
        sa.Column("high_24h", sa.String(64), nullable=False),
        sa.Column("low_24h", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, default="seeded-paper"),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingest_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=True),
    )
    op.create_index("ix_ticker_symbol_time", "tickers", ["symbol", "ingest_time"])

    # --- Audit Events ---
    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False, index=True),
        sa.Column("actor", sa.String(64), nullable=False, index=True),
        sa.Column("resource_type", sa.String(32), nullable=False, index=True),
        sa.Column("resource_id", sa.String(64), nullable=False, index=True),
        sa.Column("details", postgresql.JSONB, nullable=False, default=dict),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )

    # --- Reconciliation Logs ---
    op.create_table(
        "reconciliation_logs",
        sa.Column("reconciliation_id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False, index=True),
        sa.Column("status", sa.String(16), nullable=False, index=True),
        sa.Column("details", sa.Text, nullable=False),
        sa.Column("summary", postgresql.JSONB, nullable=False, default=dict),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )

    # --- Resolution Records ---
    op.create_table(
        "resolution_records",
        sa.Column("resolution_id", sa.String(64), primary_key=True),
        sa.Column("reconciliation_id", sa.String(64), nullable=False, index=True),
        sa.Column("account_id", sa.String(64), nullable=False, index=True),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )

    # --- Approvals ---
    op.create_table(
        "approvals",
        sa.Column("approval_id", sa.String(64), primary_key=True),
        sa.Column("resource_type", sa.String(32), nullable=False, index=True),
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("requested_by", sa.String(64), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("details", sa.Text, nullable=False, default=""),
        sa.Column("status", sa.String(16), nullable=False, default="pending", index=True),
        sa.Column("decided_by", sa.String(64), nullable=True),
        sa.Column("reject_reason", sa.Text, nullable=True),
        sa.Column("ttl_seconds", sa.Integer, nullable=False, default=86400),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- Kill Switch ---
    op.create_table(
        "kill_switch_state",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("status", sa.String(16), nullable=False, default="inactive"),
        sa.Column("triggered_by", sa.String(64), nullable=True),
        sa.Column("trigger_reason", sa.Text, nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovered_by", sa.String(64), nullable=True),
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- Backtests ---
    op.create_table(
        "backtests",
        sa.Column("backtest_id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False, index=True),
        sa.Column("strategy_id", sa.String(64), nullable=False, index=True),
        sa.Column("strategy_version", sa.String(32), nullable=False),
        sa.Column("parameters", postgresql.JSONB, nullable=False, default=dict),
        sa.Column("data_snapshot", sa.String(128), nullable=False),
        sa.Column("fee_model", sa.String(32), nullable=False),
        sa.Column("slippage_model", sa.String(32), nullable=False),
        sa.Column("run_environment", sa.String(32), nullable=False),
        sa.Column("initial_capital", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=True, unique=True),
        sa.Column("code_ref", sa.String(256), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, default="running", index=True),
        sa.Column("net_profit", sa.String(64), nullable=True),
        sa.Column("sharpe_ratio", sa.String(64), nullable=True),
        sa.Column("max_drawdown", sa.String(64), nullable=True),
        sa.Column("win_rate", sa.String(64), nullable=True),
        sa.Column("total_trades", sa.Integer, nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- Portfolio Targets ---
    op.create_table(
        "portfolio_targets",
        sa.Column("target_id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False, index=True),
        sa.Column("strategy_id", sa.String(64), nullable=False, index=True),
        sa.Column("strategy_version", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("target_quantity", sa.String(64), nullable=False),
        sa.Column("current_quantity", sa.String(64), nullable=False),
        sa.Column("target_weight", sa.String(64), nullable=True),
        sa.Column("delta", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- Agent Tasks ---
    op.create_table(
        "agent_tasks",
        sa.Column("task_id", sa.String(64), primary_key=True),
        sa.Column("task_type", sa.String(32), nullable=False, index=True),
        sa.Column("status", sa.String(16), nullable=False, default="pending", index=True),
        sa.Column("input_payload", postgresql.JSONB, nullable=False, default=dict),
        sa.Column("output_payload", postgresql.JSONB, nullable=False, default=dict),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("requested_by", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- Alerts ---
    op.create_table(
        "alerts",
        sa.Column("alert_id", sa.String(64), primary_key=True),
        sa.Column("severity", sa.String(16), nullable=False, index=True),
        sa.Column("category", sa.String(32), nullable=False, index=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, default="open", index=True),
        sa.Column("context", postgresql.JSONB, nullable=False, default=dict),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("acknowledged_by", sa.String(64), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- Exchange Connections ---
    op.create_table(
        "exchange_connections",
        sa.Column("connection_id", sa.String(64), primary_key=True),
        sa.Column("exchange", sa.String(32), nullable=False, index=True),
        sa.Column("status", sa.String(16), nullable=False, default="disconnected", index=True),
        sa.Column("config", postgresql.JSONB, nullable=False, default=dict),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- AI Model Providers ---
    op.create_table(
        "ai_model_providers",
        sa.Column("provider_id", sa.String(64), primary_key=True),
        sa.Column("provider_type", sa.String(32), nullable=False, index=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False, default=dict),
        sa.Column("status", sa.String(16), nullable=False, default="inactive", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- MTM Logs ---
    op.create_table(
        "mtm_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("position_id", sa.String(64), nullable=False, index=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("mark_price", sa.String(64), nullable=False),
        sa.Column("unrealized_pnl", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table("mtm_logs")
    op.drop_table("ai_model_providers")
    op.drop_table("exchange_connections")
    op.drop_table("alerts")
    op.drop_table("agent_tasks")
    op.drop_table("portfolio_targets")
    op.drop_table("backtests")
    op.drop_table("kill_switch_state")
    op.drop_table("approvals")
    op.drop_table("resolution_records")
    op.drop_table("reconciliation_logs")
    op.drop_table("audit_events")
    op.drop_table("tickers")
    op.drop_table("symbols")
    op.drop_table("strategy_runs")
    op.drop_table("strategies")
    op.drop_table("positions")
    op.drop_table("risk_decisions")
    op.drop_table("fill_records")
    op.drop_table("orders")
