import pickle


def test_persistence_snapshot_is_checksummed(tmp_path, monkeypatch):
    from app.core.config import settings
    from app.db.memory import InMemoryStore

    monkeypatch.setattr(settings, "storage_enabled", True)
    path = tmp_path / "quant-store.pkl"
    monkeypatch.setattr(settings, "storage_path", str(path))

    first = InMemoryStore()
    first.save()
    with path.open("rb") as handle:
        envelope = pickle.load(handle)
    assert envelope["format"] == "quant-snapshot-v1"
    assert envelope["sha256"]
    assert isinstance(envelope["payload"], bytes)

    restored = InMemoryStore()
    assert "BTCUSDT" in restored.symbols
    assert restored.persistence_error is None

    envelope["payload"] = envelope["payload"] + b"tampered"
    with path.open("wb") as handle:
        pickle.dump(envelope, handle)
    corrupted = InMemoryStore()
    assert "checksum mismatch" in (corrupted.persistence_error or "")


def test_db_store_save_with_enums_and_strings():
    from unittest.mock import MagicMock
    from app.db.db_store import DBStore
    from app.models.domain import (
        Order, Position, Symbol, FillRecord, Strategy, PortfolioTarget, StrategyRun,
        RiskPreflightResult, Backtest, Approval, ReconciliationLog, ResolutionRecord,
        AuditEvent, KillSwitchState
    )
    from app.models.enums import (
        MarketType, OrderSide, OrderType, OrderStatus, TradeMode,
        RiskDecision, ApprovalResourceType, ApprovalStatus, BacktestStatus, KillSwitchStatus,
        ReconciliationStatus, ResolutionDecision
    )

    store = DBStore.__new__(DBStore)
    store.orders = {}
    store.risk_decisions = {}
    store.positions = {}
    store.audit_events = []
    store.strategies = {}
    store.symbols = {}
    store.tickers = {}
    store.backtests = {}
    store.fills = {}
    store.reconciliation_logs = []
    store.approvals = {}
    store.portfolio_targets = {}
    store.mtm_logs = []
    store.resolution_records = []
    store.strategy_runs = {}
    store.alerts = {}
    store.model_providers = {}
    store.exchange_connections = {}
    store.kill_switch_state = None
    import threading
    store._lock = threading.RLock()
    store.persistence_error = None

    # Add entities with Enum
    order_enum = Order(
        client_order_id="ord-1",
        account_id="acc-1",
        strategy_id="strat-1",
        strategy_version="1.0",
        symbol="BTCUSDT",
        market_type=MarketType.SPOT,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity="1.0",
        mode=TradeMode.PAPER,
    )
    order_enum.status = OrderStatus.NEW
    store.orders["ord-1"] = order_enum

    # Add entities with str
    order_str = Order(
        client_order_id="ord-2",
        account_id="acc-1",
        strategy_id="strat-1",
        strategy_version="1.0",
        symbol="BTCUSDT",
        market_type="spot",
        side="buy",
        order_type="limit",
        quantity="1.0",
        mode="paper",
    )
    order_str.status = "open"
    store.orders["ord-2"] = order_str

    # Add symbol with str market_type
    sym_str = Symbol(
        symbol="ETHUSDT",
        base_asset="ETH",
        quote_asset="USDT",
        market_type="spot",
    )
    sym_str.status = "active"
    store.symbols["ETHUSDT"] = sym_str

    # Add fill with str
    fill_str = FillRecord(
        fill_id="f-1",
        client_order_id="ord-2",
        account_id="acc-1",
        symbol="BTCUSDT",
        side="buy",
        fill_quantity="1.0",
        fill_price="50000.0",
        trade_mode="paper",
    )
    store.fills["f-1"] = fill_str

    # Add position with str
    pos_str = Position(
        position_id="pos-1",
        account_id="acc-1",
        symbol="BTCUSDT",
        market_type="spot",
        side="long",
        quantity="1.0",
        entry_price="50000.0",
        current_price="51000.0",
        unrealized_pnl="1000.0",
        realized_pnl="0.0",
    )
    store.positions["pos-1"] = pos_str

    # Add risk decision with str
    dec_str = RiskPreflightResult(
        decision_id="dec-1",
        decision="approved",
        account_id="acc-1",
        symbol="BTCUSDT",
        side="buy",
        quantity="1.0",
        strategy_id="strat-1",
        strategy_version="1.0",
        mode="paper",
    )
    store.risk_decisions["dec-1"] = dec_str

    # Add backtest with str
    bt_str = Backtest(
        backtest_id="bt-1",
        strategy_id="strat-1",
        strategy_version="1.0",
        parameters={},
        data_snapshot={},
        fee_model={},
        slippage_model={},
        run_environment="python",
        initial_capital="100000",
        account_id="acc-1",
        mode="paper",
    )
    bt_str.status = "completed"
    store.backtests["bt-1"] = bt_str

    # Add strategy with str
    strat_str = Strategy(
        strategy_id="strat-1",
        name="TestStrategy",
        version="1.0",
        description="desc",
        parameters={},
        status="active",
        code_ref="ref",
    )
    store.strategies["strat-1"] = strat_str

    # Add portfolio target with str
    pt_str = PortfolioTarget(
        target_id="pt-1",
        account_id="acc-1",
        strategy_id="strat-1",
        strategy_version="1.0",
        symbol="BTCUSDT",
        target_quantity="1.0",
        current_quantity="0.5",
        target_weight="0.1",
        mode="paper",
    )
    store.portfolio_targets["pt-1"] = pt_str

    # Add strategy run with str
    sr_str = StrategyRun(
        run_id="sr-1",
        strategy_id="strat-1",
        strategy_version="1.0",
        account_id="acc-1",
        mode="paper",
        dry_run=True,
        status="success",
        data_quality={},
        signals=[],
    )
    store.strategy_runs["sr-1"] = sr_str

    # Add approval with str
    appr_str = Approval(
        approval_id="appr-1",
        resource_type="kill_switch",
        resource_id="ks-1",
        requested_by="admin",
        title="Test Approval",
        details={},
    )
    appr_str.status = "approved"
    store.approvals["appr-1"] = appr_str

    # Add reconciliation log with str
    rec_log = ReconciliationLog(
        reconciliation_id="rec-1",
        account_id="acc-1",
        status="healthy",
        details={},
        summary="ok",
    )
    store.reconciliation_logs.append(rec_log)

    # Add resolution record with str
    res_rec = ResolutionRecord(
        resolution_id="res-1",
        reconciliation_id="rec-1",
        account_id="acc-1",
        decision="accept_system",
        reason="verified",
        actor="admin",
    )
    store.resolution_records.append(res_rec)

    # Add audit event with str
    audit_evt = AuditEvent(
        event_id="evt-1",
        event_type="order.create",
        actor="system",
        resource_type="order",
        resource_id="ord-1",
        details={},
    )
    store.audit_events.append(audit_evt)

    # Add kill switch state with str
    ks_state = KillSwitchState()
    ks_state.status = "triggered"
    ks_state.triggered_by = "risk"
    ks_state.trigger_reason = "drawdown"
    store.kill_switch_state = ks_state

    mock_session = MagicMock()
    mock_models = MagicMock()

    # Execute all saves — ensuring no AttributeError occurs
    store._save_orders(mock_session, mock_models)
    store._save_fills(mock_session, mock_models)
    store._save_risk_decisions(mock_session, mock_models)
    store._save_positions(mock_session, mock_models)
    store._save_strategies(mock_session, mock_models)
    store._save_symbols(mock_session, mock_models)
    store._save_audit_events(mock_session, mock_models)
    store._save_reconciliation(mock_session, mock_models)
    store._save_resolutions(mock_session, mock_models)
    store._save_approvals(mock_session, mock_models)
    store._save_kill_switch(mock_session, mock_models)
    store._save_backtests(mock_session, mock_models)
    store._save_portfolio_targets(mock_session, mock_models)
    store._save_strategy_runs(mock_session, mock_models)
