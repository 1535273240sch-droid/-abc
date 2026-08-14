"""Database-backed store that maintains the same interface as InMemoryStore.

Strategy
-------
``DBStore`` inherits from ``InMemoryStore`` and overrides ``_load`` and
``save``.  On startup it loads all rows from the relational tables into
the in-memory dicts; on ``save()`` it upserts the in-memory state back
into the relational tables.

This gives us:
* proper relational schema (queryable, indexable, backup-able)
* backward-compatible interface (services unchanged)
* standard Alembic migrations for schema evolution

Limitations (addressed in P1-3 distributed-architecture phase):
* still single-writer (one process owns the in-memory state)
* not horizontally scalable (no multi-instance coordination)

Transition path: services can be gradually refactored to use the
session-scoped repositories directly, at which point the in-memory
dicts can be dropped.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.memory import InMemoryStore
from app.models.domain import (
    Approval,
    AuditEvent,
    Backtest,
    FillRecord,
    KillSwitchState,
    Order,
    PortfolioTarget,
    Position,
    ReconciliationLog,
    ResolutionRecord,
    RiskPreflightResult,
    Strategy,
    StrategyRun,
    Symbol,
    Ticker,
    utcnow,
)
from app.models.enums import (
    ApprovalResourceType,
    ApprovalStatus,
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

logger = logging.getLogger(__name__)


def _to_enum(enum_cls: type, value: str | None):
    if value is None:
        return None
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        return None


class DBStore(InMemoryStore):
    """PostgreSQL-backed store that preserves the InMemoryStore interface."""

    def __init__(self):
        # Skip InMemoryStore.__init__ persistence (we do our own DB load)
        # but still initialise all the service objects.
        self.orders: dict[str, Any] = {}
        self.risk_decisions: dict[str, Any] = {}
        self.positions: dict[str, Any] = {}
        self.audit_events: list[Any] = []
        self.strategies: dict[str, Any] = {}
        self.symbols: dict[str, Any] = {}
        self.tickers: dict[str, Any] = {}
        self.backtests: dict[str, Any] = {}
        self.fills: dict[str, Any] = {}
        self.reconciliation_logs: list[Any] = []
        self.approvals: dict[str, Any] = {}
        self.portfolio_targets: dict[str, Any] = {}
        self.mtm_logs: list[Any] = []
        self.resolution_records: list[Any] = []
        self.agent_tasks: dict[str, Any] = {}
        self.strategy_runs: dict[str, Any] = {}
        self.alerts: dict[str, Any] = {}
        self.model_providers: dict[str, Any] = {}
        self.exchange_connections: dict[str, Any] = {}
        self.kill_switch_state: Any = None
        self.strategy_states: dict = {}

        # Initialise services (same as InMemoryStore)
        self._init_services()

        import threading
        self._lock = threading.RLock()
        self.persistence_error: str | None = None

        # Load from database
        self._load()

    def _init_services(self):
        """Initialise service objects — mirrors InMemoryStore.__init__."""
        from app.services.approval_service import ApprovalService
        from app.services.agent_service import AgentTaskService
        from app.services.alert_service import AlertService
        from app.services.ai_service import AIService
        from app.services.audit_service import AuditService
        from app.services.backtest_service import BacktestService
        from app.services.control_service import ControlService
        from app.services.kill_switch_service import KillSwitchService
        from app.services.market_service import MarketService
        from app.services.order_execution_service import OrderExecutionService
        from app.services.order_service import OrderService
        from app.services.portfolio_service import PortfolioTargetService
        from app.services.position_service import PositionService
        from app.services.reconciliation_service import ReconciliationService
        from app.services.risk_service import RiskService
        from app.services.strategy_runtime_service import StrategyRuntimeService
        from app.services.strategy_service import StrategyService
        from app.adapters.adapter_service import AdapterService
        from app.services.kline_service import KlineService
        from app.services.alert_notification_service import AlertNotificationService
        from app.services.historical_data_service import HistoricalDataService
        from app.services.live_guard_service import LiveGuardService
        from app.services.live_mode_service import LiveModeService
        from app.services.live_risk_service import LiveRiskService
        from app.services.credential_service import CredentialService

        self.market_service = MarketService(self)
        self.risk_service = RiskService(self)
        self.order_service = OrderService(self)
        self.position_service = PositionService(self)
        self.strategy_service = StrategyService(self)
        self.audit_service = AuditService(self)
        self.backtest_service = BacktestService(self)
        self.execution_service = OrderExecutionService(self)
        self.reconciliation_service = ReconciliationService(self)
        self.approval_service = ApprovalService(self)
        self.kill_switch_service = KillSwitchService(self)
        self.live_mode_service = LiveModeService(self)
        self.live_risk_service = LiveRiskService(self)
        self.credential_service = CredentialService(self)
        self.historical_data_service = HistoricalDataService(kline_service=self.kline_service)
        self.adapter_service = AdapterService(self)
        self.portfolio_target_service = PortfolioTargetService(self)
        self.agent_task_service = AgentTaskService(self)
        self.strategy_runtime_service = StrategyRuntimeService(self)
        self.alert_service = AlertService(self)
        self.control_service = ControlService(self)
        self.ai_service = AIService(self)
        self.kline_service = KlineService()
        self.alert_notification_service = AlertNotificationService(self)
        self.live_guard_service = LiveGuardService(self)

        if settings.storage_enabled:
            self.historical_data_service.connect_persistence(
                persist_fn=self._persist_historical_klines,
                load_fn=self._load_historical_klines,
            )

    # ─────────────────── Load from DB ───────────────────

    def _load(self) -> None:
        try:
            from app.db.database import session_scope
            from app.db import orm_models as M

            with session_scope() as session:
                # Orders
                for row in session.query(M.OrderModel).all():
                    order = Order(
                        client_order_id=row.client_order_id,
                        account_id=row.account_id,
                        strategy_id=row.strategy_id,
                        strategy_version=row.strategy_version,
                        symbol=row.symbol,
                        market_type=MarketType(row.market_type),
                        side=OrderSide(row.side),
                        order_type=OrderType(row.order_type),
                        quantity=row.quantity,
                        limit_price=row.limit_price,
                        mode=TradeMode(row.mode),
                        risk_decision_id=row.risk_decision_id,
                    )
                    order.status = OrderStatus(row.status)
                    order.filled_quantity = row.filled_quantity
                    order.average_price = row.average_price
                    order.reject_reason = row.reject_reason
                    order.created_at = row.created_at
                    order.updated_at = row.updated_at
                    self.orders[order.client_order_id] = order

                # Risk decisions
                for row in session.query(M.RiskDecisionModel).all():
                    decision = RiskPreflightResult(
                        decision_id=row.decision_id,
                        decision=RiskDecision(row.decision),
                        account_id=row.account_id,
                        symbol=row.symbol,
                        side=OrderSide(row.side),
                        quantity=row.quantity,
                        strategy_id=row.strategy_id,
                        strategy_version=row.strategy_version,
                        reject_reason=row.reject_reason,
                        remaining_risk_budget=row.remaining_risk_budget,
                        rules_checked=row.rules_checked or [],
                        mode=TradeMode(row.mode),
                        price=row.price,
                        notional=row.notional,
                    )
                    decision.consumed_by = row.consumed_by
                    decision.created_at = row.created_at
                    self.risk_decisions[decision.decision_id] = decision

                # Fills
                for row in session.query(M.FillRecordModel).all():
                    fill = FillRecord(
                        fill_id=row.fill_id,
                        client_order_id=row.client_order_id,
                        account_id=row.account_id,
                        symbol=row.symbol,
                        side=OrderSide(row.side),
                        fill_quantity=row.fill_quantity,
                        fill_price=row.fill_price,
                        trade_mode=TradeMode(row.trade_mode),
                    )
                    fill.created_at = row.created_at
                    self.fills[fill.fill_id] = fill

                # Positions
                for row in session.query(M.PositionModel).all():
                    pos = Position(
                        position_id=row.position_id,
                        account_id=row.account_id,
                        symbol=row.symbol,
                        market_type=MarketType(row.market_type),
                        side=OrderSide(row.side),
                        quantity=row.quantity,
                        entry_price=row.entry_price,
                        current_price=row.current_price,
                        unrealized_pnl=row.unrealized_pnl,
                        realized_pnl=row.realized_pnl,
                    )
                    pos.created_at = row.created_at
                    pos.updated_at = row.updated_at
                    self.positions[pos.position_id] = pos

                # Strategies
                for row in session.query(M.StrategyModel).all():
                    strat = Strategy(
                        strategy_id=row.strategy_id,
                        name=row.name,
                        version=row.version,
                        description=row.description,
                        parameters=row.parameters or {},
                        status=row.status,
                        code_ref=row.code_ref,
                        owner=row.owner,
                        kind=row.kind,
                    )
                    strat.created_at = row.created_at
                    strat.updated_at = row.updated_at
                    self.strategies[strat.strategy_id] = strat

                # Symbols
                for row in session.query(M.SymbolModel).all():
                    sym = Symbol(
                        symbol=row.symbol,
                        base_asset=row.base_asset,
                        quote_asset=row.quote_asset,
                        market_type=MarketType(row.market_type),
                        min_qty=row.min_qty,
                        max_qty=row.max_qty,
                        tick_size=row.tick_size,
                        status=row.status,
                    )
                    self.symbols[sym.symbol] = sym

                # Tickers (latest per symbol)
                from sqlalchemy import func
                latest_ticker_subq = (
                    session.query(
                        M.TickerModel.symbol,
                        func.max(M.TickerModel.id).label("max_id"),
                    )
                    .group_by(M.TickerModel.symbol)
                    .subquery()
                )
                ticker_rows = (
                    session.query(M.TickerModel)
                    .join(
                        latest_ticker_subq,
                        M.TickerModel.id == latest_ticker_subq.c.max_id,
                    )
                    .all()
                )
                for row in ticker_rows:
                    ticker = Ticker(
                        symbol=row.symbol,
                        last_price=row.last_price,
                        bid_price=row.bid_price,
                        ask_price=row.ask_price,
                        volume_24h=row.volume_24h,
                        change_24h=row.change_24h,
                        high_24h=row.high_24h,
                        low_24h=row.low_24h,
                        source=row.source,
                        event_time=row.event_time,
                        ingest_time=row.ingest_time,
                        sequence=row.sequence,
                    )
                    self.tickers[ticker.symbol] = ticker

                # Audit events
                for row in session.query(M.AuditEventModel).order_by(M.AuditEventModel.created_at).all():
                    event = AuditEvent(
                        event_id=row.event_id,
                        event_type=row.event_type,
                        actor=row.actor,
                        resource_type=row.resource_type,
                        resource_id=row.resource_id,
                        details=row.details or {},
                        ip_address=row.ip_address,
                        trace_id=row.trace_id,
                    )
                    event.created_at = row.created_at
                    self.audit_events.append(event)

                # Reconciliation logs
                for row in session.query(M.ReconciliationLogModel).all():
                    log = ReconciliationLog(
                        reconciliation_id=row.reconciliation_id,
                        account_id=row.account_id,
                        status=ReconciliationStatus(row.status),
                        details=row.details,
                        summary=row.summary or {},
                    )
                    log.created_at = row.created_at
                    self.reconciliation_logs.append(log)

                # Resolution records
                for row in session.query(M.ResolutionRecordModel).all():
                    rec = ResolutionRecord(
                        resolution_id=row.resolution_id,
                        reconciliation_id=row.reconciliation_id,
                        account_id=row.account_id,
                        decision=ResolutionDecision(row.decision),
                        reason=row.reason,
                        actor=row.actor,
                        idempotency_key=row.idempotency_key,
                    )
                    rec.created_at = row.created_at
                    self.resolution_records.append(rec)

                # Approvals
                for row in session.query(M.ApprovalModel).all():
                    approval = Approval(
                        approval_id=row.approval_id,
                        resource_type=ApprovalResourceType(row.resource_type),
                        resource_id=row.resource_id,
                        requested_by=row.requested_by,
                        title=row.title,
                        details=row.details,
                        ttl_seconds=row.ttl_seconds,
                    )
                    approval.status = ApprovalStatus(row.status)
                    approval.decided_by = row.decided_by
                    approval.reject_reason = row.reject_reason
                    approval.created_at = row.created_at
                    approval.decided_at = row.decided_at
                    approval.expires_at = row.expires_at
                    self.approvals[approval.approval_id] = approval

                # Kill switch state
                ks_row = session.query(M.KillSwitchModel).order_by(M.KillSwitchModel.id.desc()).first()
                if ks_row:
                    ks = KillSwitchState()
                    ks.status = KillSwitchStatus(ks_row.status)
                    ks.triggered_by = ks_row.triggered_by
                    ks.trigger_reason = ks_row.trigger_reason
                    ks.triggered_at = ks_row.triggered_at
                    ks.recovered_by = ks_row.recovered_by
                    ks.recovered_at = ks_row.recovered_at
                    self.kill_switch_state = ks

                # Backtests
                for row in session.query(M.BacktestModel).all():
                    bt = Backtest(
                        backtest_id=row.backtest_id,
                        strategy_id=row.strategy_id,
                        strategy_version=row.strategy_version,
                        parameters=row.parameters,
                        data_snapshot=row.data_snapshot,
                        fee_model=row.fee_model,
                        slippage_model=row.slippage_model,
                        run_environment=row.run_environment,
                        initial_capital=row.initial_capital,
                        account_id=row.account_id,
                        mode=TradeMode(row.mode),
                        idempotency_key=row.idempotency_key,
                    )
                    bt.code_ref = row.code_ref
                    bt.status = BacktestStatus(row.status)
                    bt.net_profit = row.net_profit
                    bt.sharpe_ratio = row.sharpe_ratio
                    bt.max_drawdown = row.max_drawdown
                    bt.win_rate = row.win_rate
                    bt.total_trades = row.total_trades
                    bt.created_at = row.created_at
                    bt.completed_at = row.completed_at
                    self.backtests[bt.backtest_id] = bt

                # Portfolio targets
                for row in session.query(M.PortfolioTargetModel).all():
                    pt = PortfolioTarget(
                        target_id=row.target_id,
                        account_id=row.account_id,
                        strategy_id=row.strategy_id,
                        strategy_version=row.strategy_version,
                        symbol=row.symbol,
                        target_quantity=row.target_quantity,
                        current_quantity=row.current_quantity,
                        target_weight=row.target_weight,
                        mode=TradeMode(row.mode),
                        idempotency_key=row.idempotency_key,
                    )
                    pt.delta = row.delta
                    pt.created_at = row.created_at
                    pt.updated_at = row.updated_at
                    self.portfolio_targets[pt.target_id] = pt

                # Strategy runs
                for row in session.query(M.StrategyRunModel).all():
                    sr = StrategyRun(
                        run_id=row.run_id,
                        strategy_id=row.strategy_id,
                        strategy_version=row.strategy_version,
                        account_id=row.account_id,
                        mode=TradeMode(row.mode),
                        dry_run=row.dry_run,
                        status=row.status,
                        data_quality=row.data_quality or {},
                        signals=row.signals or [],
                        orders=row.orders or [],
                        reason=row.reason,
                    )
                    sr.created_at = row.created_at
                    sr.completed_at = row.completed_at
                    self.strategy_runs[sr.run_id] = sr

                # Alerts
                for row in session.query(M.AlertModel).all():
                    self.alerts[row.alert_id] = _row_to_alert(row)

                # Exchange connections
                for row in session.query(M.ExchangeConnectionModel).all():
                    self.exchange_connections[row.connection_id] = {
                        "connection_id": row.connection_id,
                        "exchange": row.exchange,
                        "status": row.status,
                        "config": row.config or {},
                        "connected_at": row.connected_at,
                        "disconnected_at": row.disconnected_at,
                    }

                # AI providers
                for row in session.query(M.AIProviderModel).all():
                    self.model_providers[row.provider_id] = {
                        "provider_id": row.provider_id,
                        "provider_type": row.provider_type,
                        "name": row.name,
                        "config": row.config or {},
                        "status": row.status,
                    }

                # MTM logs
                for row in session.query(M.MTMLogModel).order_by(M.MTMLogModel.created_at).all():
                    self.mtm_logs.append({
                        "id": row.id,
                        "position_id": row.position_id,
                        "symbol": row.symbol,
                        "mark_price": row.mark_price,
                        "unrealized_pnl": row.unrealized_pnl,
                        "created_at": row.created_at,
                    })

                # Historical klines → warm the kline service buffer
                from app.strategies.signal import Bar
                kline_rows = (
                    session.query(M.HistoricalKlineModel)
                    .order_by(M.HistoricalKlineModel.symbol, M.HistoricalKlineModel.period, M.HistoricalKlineModel.open_time)
                    .all()
                )
                for row in kline_rows:
                    bar = Bar(
                        symbol=row.symbol,
                        open_time=row.open_time,
                        open=Decimal(row.open),
                        high=Decimal(row.high),
                        low=Decimal(row.low),
                        close=Decimal(row.close),
                        volume=Decimal(row.volume),
                        close_time=row.close_time,
                    )
                    self.kline_service._buffers.setdefault((row.symbol, row.period), []).append(bar)

            logger.info("DBStore loaded from database: %d orders, %d positions, %d strategies",
                         len(self.orders), len(self.positions), len(self.strategies))
        except Exception as exc:  # noqa: BLE001
            self.persistence_error = f"database load failed: {str(exc)[:500]}"
            logger.error("DBStore load failed: %s", exc, exc_info=True)

    # ─────────────────── Save to DB ───────────────────

    def save(self) -> None:
        from app.core.config import settings
        if not settings.storage_enabled:
            return
        with self._lock:
            if self.persistence_error:
                return
            try:
                from app.db.database import session_scope
                from app.db import orm_models as M

                with session_scope() as session:
                    self._save_orders(session, M)
                    self._save_fills(session, M)
                    self._save_risk_decisions(session, M)
                    self._save_positions(session, M)
                    self._save_strategies(session, M)
                    self._save_symbols(session, M)
                    self._save_tickers(session, M)
                    self._save_audit_events(session, M)
                    self._save_reconciliation(session, M)
                    self._save_resolutions(session, M)
                    self._save_approvals(session, M)
                    self._save_kill_switch(session, M)
                    self._save_backtests(session, M)
                    self._save_portfolio_targets(session, M)
                    self._save_strategy_runs(session, M)
                    self._save_alerts(session, M)
                    self._save_exchange_connections(session, M)
                    self._save_ai_providers(session, M)
                    self._save_mtm_logs(session, M)
            except Exception as exc:  # noqa: BLE001
                self.persistence_error = f"database save failed: {str(exc)[:500]}"
                logger.error("DBStore save failed: %s", exc, exc_info=True)

    def _upsert(self, session, model_cls, pk_field: str, pk_value: str, data: dict):
        """Upsert a single row."""
        existing = session.get(model_cls, pk_value)
        if existing:
            for key, value in data.items():
                setattr(existing, key, value)
        else:
            session.add(model_cls(**data))

    def _save_orders(self, session, M):
        for oid, order in self.orders.items():
            self._upsert(session, M.OrderModel, "client_order_id", oid, {
                "client_order_id": oid,
                "account_id": order.account_id,
                "strategy_id": order.strategy_id,
                "strategy_version": order.strategy_version,
                "symbol": order.symbol,
                "market_type": order.market_type.value,
                "side": order.side.value,
                "order_type": order.order_type.value,
                "quantity": order.quantity,
                "limit_price": order.limit_price,
                "mode": order.mode.value,
                "risk_decision_id": order.risk_decision_id,
                "status": order.status.value,
                "filled_quantity": order.filled_quantity,
                "average_price": order.average_price,
                "reject_reason": order.reject_reason,
                "created_at": order.created_at,
                "updated_at": order.updated_at,
            })

    def _save_fills(self, session, M):
        for fid, fill in self.fills.items():
            self._upsert(session, M.FillRecordModel, "fill_id", fid, {
                "fill_id": fid,
                "client_order_id": fill.client_order_id,
                "account_id": fill.account_id,
                "symbol": fill.symbol,
                "side": fill.side.value,
                "fill_quantity": fill.fill_quantity,
                "fill_price": fill.fill_price,
                "trade_mode": fill.trade_mode.value,
                "created_at": fill.created_at,
            })

    def _save_risk_decisions(self, session, M):
        for did, dec in self.risk_decisions.items():
            self._upsert(session, M.RiskDecisionModel, "decision_id", did, {
                "decision_id": did,
                "decision": dec.decision.value,
                "account_id": dec.account_id,
                "symbol": dec.symbol,
                "side": dec.side.value,
                "quantity": dec.quantity,
                "strategy_id": dec.strategy_id,
                "strategy_version": dec.strategy_version,
                "reject_reason": dec.reject_reason,
                "remaining_risk_budget": dec.remaining_risk_budget,
                "rules_checked": dec.rules_checked,
                "mode": dec.mode.value,
                "price": dec.price,
                "notional": dec.notional,
                "consumed_by": getattr(dec, "consumed_by", None),
                "created_at": dec.created_at,
            })

    def _save_positions(self, session, M):
        for pid, pos in self.positions.items():
            self._upsert(session, M.PositionModel, "position_id", pid, {
                "position_id": pid,
                "account_id": pos.account_id,
                "symbol": pos.symbol,
                "market_type": pos.market_type.value,
                "side": pos.side.value,
                "quantity": pos.quantity,
                "entry_price": pos.entry_price,
                "current_price": pos.current_price,
                "unrealized_pnl": pos.unrealized_pnl,
                "realized_pnl": pos.realized_pnl,
                "created_at": pos.created_at,
                "updated_at": pos.updated_at,
            })

    def _save_strategies(self, session, M):
        for sid, strat in self.strategies.items():
            self._upsert(session, M.StrategyModel, "strategy_id", sid, {
                "strategy_id": sid,
                "name": strat.name,
                "version": strat.version,
                "description": strat.description,
                "parameters": strat.parameters,
                "status": strat.status,
                "code_ref": strat.code_ref,
                "owner": strat.owner,
                "kind": strat.kind,
                "created_at": strat.created_at,
                "updated_at": strat.updated_at,
            })

    def _save_symbols(self, session, M):
        for sym_str, sym in self.symbols.items():
            self._upsert(session, M.SymbolModel, "symbol", sym_str, {
                "symbol": sym_str,
                "base_asset": sym.base_asset,
                "quote_asset": sym.quote_asset,
                "market_type": sym.market_type.value,
                "min_qty": sym.min_qty,
                "max_qty": sym.max_qty,
                "tick_size": sym.tick_size,
                "status": sym.status,
            })

    def _save_tickers(self, session, M):
        # Insert new ticker rows (time-series — don't update existing)
        existing_symbols = {r.symbol for r in session.query(M.TickerModel.symbol).distinct().all()}
        for sym_str, ticker in self.tickers.items():
            latest = session.query(M.TickerModel).filter(
                M.TickerModel.symbol == sym_str
            ).order_by(M.TickerModel.id.desc()).first()

            should_insert = True
            if latest:
                if (latest.last_price == ticker.last_price and
                    latest.bid_price == ticker.bid_price and
                    latest.ask_price == ticker.ask_price):
                    should_insert = False

            if should_insert:
                session.add(M.TickerModel(
                    symbol=ticker.symbol,
                    last_price=ticker.last_price,
                    bid_price=ticker.bid_price,
                    ask_price=ticker.ask_price,
                    volume_24h=ticker.volume_24h,
                    change_24h=ticker.change_24h,
                    high_24h=ticker.high_24h,
                    low_24h=ticker.low_24h,
                    source=ticker.source,
                    event_time=ticker.event_time,
                    ingest_time=ticker.ingest_time,
                    sequence=ticker.sequence,
                ))

    def _save_audit_events(self, session, M):
        for event in self.audit_events:
            existing = session.query(M.AuditEventModel).filter(
                M.AuditEventModel.event_id == event.event_id
            ).first()
            if not existing:
                session.add(M.AuditEventModel(
                    event_id=event.event_id,
                    event_type=str(event.event_type),
                    actor=event.actor,
                    resource_type=event.resource_type,
                    resource_id=event.resource_id,
                    details=event.details,
                    ip_address=event.ip_address,
                    trace_id=event.trace_id,
                    created_at=event.created_at,
                ))

    def _save_reconciliation(self, session, M):
        for log in self.reconciliation_logs:
            existing = session.query(M.ReconciliationLogModel).filter(
                M.ReconciliationLogModel.reconciliation_id == log.reconciliation_id
            ).first()
            if not existing:
                session.add(M.ReconciliationLogModel(
                    reconciliation_id=log.reconciliation_id,
                    account_id=log.account_id,
                    status=log.status.value,
                    details=log.details,
                    summary=log.summary,
                    created_at=log.created_at,
                ))

    def _save_resolutions(self, session, M):
        for rec in self.resolution_records:
            existing = session.query(M.ResolutionRecordModel).filter(
                M.ResolutionRecordModel.resolution_id == rec.resolution_id
            ).first()
            if not existing:
                session.add(M.ResolutionRecordModel(
                    resolution_id=rec.resolution_id,
                    reconciliation_id=rec.reconciliation_id,
                    account_id=rec.account_id,
                    decision=rec.decision.value,
                    reason=rec.reason,
                    actor=rec.actor,
                    idempotency_key=rec.idempotency_key,
                    created_at=rec.created_at,
                ))

    def _save_approvals(self, session, M):
        for aid, appr in self.approvals.items():
            self._upsert(session, M.ApprovalModel, "approval_id", aid, {
                "approval_id": aid,
                "resource_type": appr.resource_type.value,
                "resource_id": appr.resource_id,
                "requested_by": appr.requested_by,
                "title": appr.title,
                "details": appr.details,
                "status": appr.status.value,
                "decided_by": appr.decided_by,
                "reject_reason": appr.reject_reason,
                "ttl_seconds": appr.ttl_seconds,
                "created_at": appr.created_at,
                "decided_at": appr.decided_at,
                "expires_at": appr.expires_at,
            })

    def _save_kill_switch(self, session, M):
        if self.kill_switch_state:
            ks = self.kill_switch_state
            session.add(M.KillSwitchModel(
                status=ks.status.value,
                triggered_by=ks.triggered_by,
                trigger_reason=ks.trigger_reason,
                triggered_at=ks.triggered_at,
                recovered_by=ks.recovered_by,
                recovered_at=ks.recovered_at,
            ))

    def _save_backtests(self, session, M):
        for bid, bt in self.backtests.items():
            self._upsert(session, M.BacktestModel, "backtest_id", bid, {
                "backtest_id": bid,
                "account_id": bt.account_id,
                "strategy_id": bt.strategy_id,
                "strategy_version": bt.strategy_version,
                "parameters": bt.parameters,
                "data_snapshot": bt.data_snapshot,
                "fee_model": bt.fee_model,
                "slippage_model": bt.slippage_model,
                "run_environment": bt.run_environment,
                "initial_capital": bt.initial_capital,
                "mode": bt.mode.value,
                "idempotency_key": bt.idempotency_key,
                "code_ref": bt.code_ref,
                "status": bt.status.value,
                "net_profit": bt.net_profit,
                "sharpe_ratio": bt.sharpe_ratio,
                "max_drawdown": bt.max_drawdown,
                "win_rate": bt.win_rate,
                "total_trades": bt.total_trades,
                "created_at": bt.created_at,
                "completed_at": bt.completed_at,
            })

    def _save_portfolio_targets(self, session, M):
        for tid, pt in self.portfolio_targets.items():
            self._upsert(session, M.PortfolioTargetModel, "target_id", tid, {
                "target_id": tid,
                "account_id": pt.account_id,
                "strategy_id": pt.strategy_id,
                "strategy_version": pt.strategy_version,
                "symbol": pt.symbol,
                "target_quantity": pt.target_quantity,
                "current_quantity": pt.current_quantity,
                "target_weight": pt.target_weight,
                "delta": pt.delta,
                "mode": pt.mode.value,
                "idempotency_key": pt.idempotency_key,
                "created_at": pt.created_at,
                "updated_at": pt.updated_at,
            })

    def _save_strategy_runs(self, session, M):
        for rid, sr in self.strategy_runs.items():
            self._upsert(session, M.StrategyRunModel, "run_id", rid, {
                "run_id": rid,
                "strategy_id": sr.strategy_id,
                "strategy_version": sr.strategy_version,
                "account_id": sr.account_id,
                "mode": sr.mode.value,
                "dry_run": sr.dry_run,
                "status": sr.status,
                "data_quality": sr.data_quality,
                "signals": sr.signals,
                "orders": sr.orders,
                "reason": sr.reason,
                "created_at": sr.created_at,
                "completed_at": sr.completed_at,
            })

    def _save_alerts(self, session, M):
        for aid, alert in self.alerts.items():
            data = {
                "alert_id": aid,
                "severity": alert.get("severity", "info"),
                "category": alert.get("category", "general"),
                "title": alert.get("title", ""),
                "message": alert.get("message", ""),
                "status": alert.get("status", "open"),
                "context": alert.get("context", {}),
                "created_at": alert.get("created_at", utcnow()),
                "acknowledged_by": alert.get("acknowledged_by"),
                "acknowledged_at": alert.get("acknowledged_at"),
            }
            self._upsert(session, M.AlertModel, "alert_id", aid, data)

    def _save_exchange_connections(self, session, M):
        for cid, conn in self.exchange_connections.items():
            self._upsert(session, M.ExchangeConnectionModel, "connection_id", cid, {
                "connection_id": cid,
                "exchange": conn.get("exchange", ""),
                "status": conn.get("status", "disconnected"),
                "config": conn.get("config", {}),
                "connected_at": conn.get("connected_at"),
                "disconnected_at": conn.get("disconnected_at"),
                "created_at": conn.get("created_at", utcnow()),
            })

    def _save_ai_providers(self, session, M):
        for pid, prov in self.model_providers.items():
            self._upsert(session, M.AIProviderModel, "provider_id", pid, {
                "provider_id": pid,
                "provider_type": prov.get("provider_type", ""),
                "name": prov.get("name", ""),
                "config": prov.get("config", {}),
                "status": prov.get("status", "inactive"),
                "created_at": prov.get("created_at", utcnow()),
            })

    def _save_mtm_logs(self, session, M):
        for log in self.mtm_logs:
            if isinstance(log, dict) and "id" not in log:
                session.add(M.MTMLogModel(
                    position_id=log.get("position_id", ""),
                    symbol=log.get("symbol", ""),
                    mark_price=log.get("mark_price", "0"),
                    unrealized_pnl=log.get("unrealized_pnl", "0"),
                    created_at=log.get("created_at", utcnow()),
                ))

    def _save_historical_klines(self, session, M):
        for key, bars in self.kline_service._buffers.items():
            symbol, period = key
            for bar in bars:
                data = {
                    "symbol": symbol,
                    "period": period,
                    "open_time": bar.open_time,
                    "open": str(bar.open),
                    "high": str(bar.high),
                    "low": str(bar.low),
                    "close": str(bar.close),
                    "volume": str(bar.volume),
                    "close_time": bar.close_time,
                }
                self._upsert(session, M.HistoricalKlineModel, "open_time", bar.open_time, data)

    def _persist_historical_klines(self, symbol: str, period: str, bars: list[Any]) -> None:
        if not settings.storage_enabled:
            return
        try:
            from app.db.database import session_scope
            from app.db import orm_models as M
            with session_scope() as session:
                self._save_historical_klines_for(session, M, symbol, period, bars)
        except Exception as exc:  # noqa: BLE001
            logger.error("historical_kline_persist_failed: %s", exc, exc_info=True)

    def _save_historical_klines_for(self, session, M, symbol: str, period: str, bars: list[Any]) -> None:
        for bar in bars:
            data = {
                "symbol": symbol,
                "period": period,
                "open_time": bar.open_time,
                "open": str(bar.open),
                "high": str(bar.high),
                "low": str(bar.low),
                "close": str(bar.close),
                "volume": str(bar.volume),
                "close_time": bar.close_time,
            }
            self._upsert(session, M.HistoricalKlineModel, "open_time", bar.open_time, data)

    def _load_historical_klines(self, symbol: str, period: str, limit: int) -> list[Any]:
        if not settings.storage_enabled:
            return []
        try:
            from app.db.database import session_scope
            from app.db import orm_models as M
            with session_scope() as session:
                rows = (
                    session.query(M.HistoricalKlineModel)
                    .filter_by(symbol=symbol.upper(), period=period)
                    .order_by(M.HistoricalKlineModel.open_time.desc())
                    .limit(limit)
                    .all()
                )
                out = []
                for row in reversed(rows):
                    out.append(Bar(
                        symbol=row.symbol,
                        open_time=row.open_time,
                        open=Decimal(row.open),
                        high=Decimal(row.high),
                        low=Decimal(row.low),
                        close=Decimal(row.close),
                        volume=Decimal(row.volume),
                        close_time=row.close_time,
                    ))
                return out
        except Exception as exc:  # noqa: BLE001
            logger.error("historical_kline_load_failed: %s", exc, exc_info=True)
            return []


def _row_to_alert(row):
    return {
        "alert_id": row.alert_id,
        "severity": row.severity,
        "category": row.category,
        "title": row.title,
        "message": row.message,
        "status": row.status,
        "context": row.context or {},
        "created_at": row.created_at,
        "acknowledged_by": row.acknowledged_by,
        "acknowledged_at": row.acknowledged_at,
    }
