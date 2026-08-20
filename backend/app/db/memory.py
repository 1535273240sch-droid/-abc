import logging
import os
import pickle
import hashlib
import hmac
import tempfile
import threading
from pathlib import Path
from typing import Any

from app.adapters.adapter_service import AdapterService
from app.core.config import settings
from app.services.approval_service import ApprovalService
from app.services.audit_service import AuditService
from app.services.agent_service import AgentTaskService
from app.services.backtest_service import BacktestService
from app.services.kill_switch_service import KillSwitchService
from app.services.market_service import MarketService
from app.services.kline_service import KlineService
from app.services.alert_notification_service import AlertNotificationService
from app.services.historical_data_service import HistoricalDataService
from app.services.live_guard_service import LiveGuardService
from app.services.live_mode_service import LiveModeService
from app.services.live_risk_service import LiveRiskService
from app.services.credential_service import CredentialService
from app.services.order_execution_service import OrderExecutionService
from app.services.order_service import OrderService
from app.services.portfolio_service import PortfolioTargetService
from app.services.position_service import PositionService
from app.services.reconciliation_service import ReconciliationService
from app.services.risk_service import RiskService
from app.services.strategy_service import StrategyService
from app.services.strategy_runtime_service import StrategyRuntimeService
from app.services.alert_service import AlertService
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)


class InMemoryStore:
    _persistence_format = "quant-snapshot-v1"

    def __init__(self, load_from_db: bool = True):
        self._lock = threading.Lock()
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
        self.strategy_states: dict = {}
        self.alerts: dict[str, Any] = {}
        self.model_providers: dict[str, Any] = {}
        self.exchange_connections: dict[str, Any] = {}
        self.kill_switch_state: Any = None

        self.market_service = MarketService(self)
        self.risk_service = RiskService(self)
        self.kline_service = KlineService()
        self.alert_notification_service = AlertNotificationService(self)
        self.live_guard_service = LiveGuardService(self)
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
        from app.services.control_service import ControlService
        self.control_service = ControlService(self)
        self.ai_service = AIService(self)
        from app.services.alpha_mining_service import AlphaMiningService
        from app.services.portfolio_optimizer_service import PortfolioOptimizerService
        from app.services.strategy_evolution_service import StrategyEvolutionService
        self.alpha_mining_service = AlphaMiningService(self)
        self.portfolio_optimizer_service = PortfolioOptimizerService(self)
        self.strategy_evolution_service = StrategyEvolutionService(self)
        from app.services.performance_analytics_service import PerformanceAnalyticsService
        self.performance_analytics_service = PerformanceAnalyticsService(self)
        from app.services.kline_analysis_service import KlineAnalysisService
        self.kline_analysis_service = KlineAnalysisService(self)

        self._lock = threading.RLock()
        self.persistence_error: str | None = None
        if settings.storage_enabled:
            self._load()

    _persisted_fields = (
        "orders",
        "risk_decisions",
        "positions",
        "audit_events",
        "strategies",
        "symbols",
        "tickers",
        "backtests",
        "fills",
        "reconciliation_logs",
        "approvals",
        "portfolio_targets",
        "mtm_logs",
        "resolution_records",
        "agent_tasks",
        "strategy_runs",
        "alerts",
        "model_providers",
        "exchange_connections",
        "kill_switch_state",
        "strategy_states",
    )

    def _apply_state(self, state: Any) -> None:
        if not isinstance(state, dict):
            raise ValueError("invalid persistence state")
        for field in self._persisted_fields:
            value = state.get(field)
            if value is not None:
                setattr(self, field, value)
        self._purge_legacy_risk_decisions()

    def _purge_legacy_risk_decisions(self) -> None:
        """一次性清理旧快照中的遗留格式风控决策。

        升级前落盘的 APPROVED 决策没有 consumed_by/notional 属性，
        getattr 防御式读取后会既不单次消费也不核验 notional，
        可被无限复用并抬价下单，绕过新防线。决策是短生命周期对象，
        清理无业务损失。
        """
        legacy_ids = [
            decision_id
            for decision_id, decision in self.risk_decisions.items()
            if not hasattr(decision, "consumed_by")
        ]
        if legacy_ids:
            for decision_id in legacy_ids:
                del self.risk_decisions[decision_id]
            logger.info(
                "purged %d legacy risk decision(s) without consumed_by from snapshot: %s",
                len(legacy_ids),
                ", ".join(legacy_ids),
            )

    def _decode_snapshot(self, state: Any) -> dict:
        if isinstance(state, dict) and state.get("format") == self._persistence_format:
            payload = state.get("payload")
            checksum = state.get("sha256")
            if not isinstance(payload, bytes) or not isinstance(checksum, str):
                raise ValueError("invalid persistence envelope")
            actual = hashlib.sha256(payload).hexdigest()
            if not hmac.compare_digest(actual, checksum):
                raise ValueError("persistence snapshot checksum mismatch")
            state = pickle.loads(payload)
        if not isinstance(state, dict):
            raise ValueError("invalid persistence state")
        return state

    def _load_file_state(self, path: Path) -> dict:
        with path.open("rb") as handle:
            return self._decode_snapshot(pickle.load(handle))

    def _load(self) -> None:
        if settings.storage_backend == "postgres":
            self._load_postgres()
            return

        path = Path(settings.storage_path)
        if not path.exists():
            return
        try:
            self._apply_state(self._load_file_state(path))
        except (OSError, EOFError, pickle.PickleError, ValueError, TypeError) as exc:
            self.persistence_error = str(exc)

    def _load_postgres(self) -> None:
        try:
            import psycopg

            with psycopg.connect(settings.postgres_dsn, connect_timeout=5) as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS quant_state_snapshot (
                        state_key TEXT PRIMARY KEY,
                        format TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        payload BYTEA NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                row = connection.execute(
                    "SELECT format, sha256, payload FROM quant_state_snapshot WHERE state_key = %s",
                    ("default",),
                ).fetchone()

            if row:
                self._apply_state(self._decode_snapshot({"format": row[0], "sha256": row[1], "payload": bytes(row[2])}))
            elif settings.storage_migration_source:
                source = Path(settings.storage_migration_source)
                if source.exists():
                    self._apply_state(self._load_file_state(source))
        except (OSError, ValueError, TypeError, ImportError) as exc:
            self.persistence_error = f"postgres storage unavailable: {str(exc)[:500]}"
        except Exception as exc:  # noqa: BLE001
            self.persistence_error = f"postgres storage unavailable: {str(exc)[:500]}"

    def save(self) -> None:
        if not settings.storage_enabled:
            return
        with self._lock:
            if self.persistence_error:
                return
            path = Path(settings.storage_path)
            state = {field: getattr(self, field) for field in self._persisted_fields}
            payload = pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)
            envelope = {
                "format": self._persistence_format,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "payload": payload,
            }
            if settings.storage_backend == "postgres":
                self._save_postgres(envelope)
                return

            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_path = tempfile.mkstemp(prefix="quant-store-", suffix=".tmp", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as handle:
                    pickle.dump(envelope, handle, protocol=pickle.HIGHEST_PROTOCOL)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_path, path)
            finally:
                if os.path.exists(temporary_path):
                    os.unlink(temporary_path)

    def _save_postgres(self, envelope: dict) -> None:
        try:
            import psycopg

            with psycopg.connect(settings.postgres_dsn, connect_timeout=5) as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS quant_state_snapshot (
                        state_key TEXT PRIMARY KEY,
                        format TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        payload BYTEA NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO quant_state_snapshot (state_key, format, sha256, payload, updated_at)
                    VALUES (%s, %s, %s, %s, now())
                    ON CONFLICT (state_key) DO UPDATE SET
                        format = EXCLUDED.format,
                        sha256 = EXCLUDED.sha256,
                        payload = EXCLUDED.payload,
                        updated_at = EXCLUDED.updated_at
                    """,
                    ("default", envelope["format"], envelope["sha256"], envelope["payload"]),
                )
        except Exception as exc:  # noqa: BLE001
            self.persistence_error = f"postgres persistence failed: {str(exc)[:500]}"

    def get_lock(self) -> threading.Lock:
        return self._lock


_store_registry: dict[str, InMemoryStore] = {}
_registry_lock = threading.Lock()


def get_store(request: Any = None) -> InMemoryStore:
    """Return the active store.

    When ``storage_backend`` is ``postgres`` and a DSN is configured,
    a :class:`DBStore` is used (proper relational tables via SQLAlchemy).
    Otherwise the plain :class:`InMemoryStore` (with optional Pickle
    persistence) is used — ideal for development and tests.
    """
    key = "default"
    if request and hasattr(request, "state") and hasattr(request.state, "store_key"):
        key = request.state.store_key
    with _registry_lock:
        if key not in _store_registry:
            if (settings.storage_backend == "postgres"
                    and settings.postgres_dsn
                    and settings.storage_enabled):
                from app.db.db_store import DBStore
                _store_registry[key] = DBStore()
            else:
                _store_registry[key] = InMemoryStore()
        return _store_registry[key]


def reset_store(key: str = "default"):
    with _registry_lock:
        if key in _store_registry:
            del _store_registry[key]
