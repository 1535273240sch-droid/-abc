from fastapi import Header, HTTPException, Request

from app.db.memory import get_store
from app.adapters.adapter_service import AdapterService
from app.services.approval_service import ApprovalService
from app.services.agent_service import AgentTaskService
from app.services.audit_service import AuditService
from app.services.backtest_service import BacktestService
from app.services.kill_switch_service import KillSwitchService
from app.services.market_service import MarketService
from app.services.order_execution_service import OrderExecutionService
from app.services.portfolio_service import PortfolioTargetService
from app.services.order_service import OrderService
from app.services.position_service import PositionService
from app.services.reconciliation_service import ReconciliationService
from app.services.risk_service import RiskService
from app.services.strategy_service import StrategyService
from app.services.strategy_runtime_service import StrategyRuntimeService
from app.services.alert_service import AlertService
from app.services.control_service import ControlService
from app.services.ai_service import AIService
from app.services.credential_service import CredentialService
from app.services.historical_data_service import HistoricalDataService
from app.services.live_mode_service import LiveModeService
from app.services.live_risk_service import LiveRiskService


def get_market_service(request: Request) -> MarketService:
    store = get_store(request)
    return store.market_service


def get_agent_task_service(request: Request) -> AgentTaskService:
    store = get_store(request)
    return store.agent_task_service


def get_risk_service(request: Request) -> RiskService:
    store = get_store(request)
    return store.risk_service


def get_order_service(request: Request) -> OrderService:
    store = get_store(request)
    return store.order_service


def get_position_service(request: Request) -> PositionService:
    store = get_store(request)
    return store.position_service


def get_strategy_service(request: Request) -> StrategyService:
    store = get_store(request)
    return store.strategy_service


def get_strategy_runtime_service(request: Request) -> StrategyRuntimeService:
    store = get_store(request)
    return store.strategy_runtime_service


def get_alert_service(request: Request) -> AlertService:
    store = get_store(request)
    return store.alert_service


def get_control_service(request: Request) -> ControlService:
    store = get_store(request)
    return store.control_service


def get_ai_service(request: Request) -> AIService:
    store = get_store(request)
    return store.ai_service


def get_audit_service(request: Request) -> AuditService:
    store = get_store(request)
    return store.audit_service


def get_backtest_service(request: Request) -> BacktestService:
    store = get_store(request)
    return store.backtest_service


def get_execution_service(request: Request) -> OrderExecutionService:
    store = get_store(request)
    return store.execution_service


def get_reconciliation_service(request: Request) -> ReconciliationService:
    store = get_store(request)
    return store.reconciliation_service


def get_approval_service(request: Request) -> ApprovalService:
    store = get_store(request)
    return store.approval_service


def get_kill_switch_service(request: Request) -> KillSwitchService:
    store = get_store(request)
    return store.kill_switch_service


def get_adapter_service(request: Request) -> AdapterService:
    store = get_store(request)
    return store.adapter_service


def get_portfolio_target_service(request: Request) -> PortfolioTargetService:
    store = get_store(request)
    return store.portfolio_target_service


def get_credential_service(request: Request) -> CredentialService:
    store = get_store(request)
    return store.credential_service


def get_live_mode_service(request: Request) -> LiveModeService:
    store = get_store(request)
    return store.live_mode_service


def get_live_risk_service(request: Request) -> LiveRiskService:
    store = get_store(request)
    return store.live_risk_service


def get_historical_data_service(request: Request) -> HistoricalDataService:
    store = get_store(request)
    return store.historical_data_service


def require_idempotency_key(x_idempotency_key: str | None = Header(None)) -> str | None:
    return x_idempotency_key


def get_alpha_mining_service(request: Request):
    store = get_store(request)
    return getattr(store, "alpha_mining_service", None)


def get_portfolio_optimizer_service(request: Request):
    store = get_store(request)
    return getattr(store, "portfolio_optimizer_service", None)


def get_strategy_evolution_service(request: Request):
    store = get_store(request)
    return getattr(store, "strategy_evolution_service", None)
