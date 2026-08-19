import pytest
from app.services.portfolio_optimizer_service import (
    solve_equal_weight,
    solve_risk_parity,
    solve_min_variance,
    solve_max_sharpe,
    _build_cov_matrix,
    PortfolioOptimizerService,
)
from app.services.strategy_evolution_service import StrategyEvolutionService
from app.db.memory import InMemoryStore


def test_portfolio_solvers():
    # 3 assets returns
    r1 = [0.01, -0.02, 0.03, 0.01, -0.01, 0.02, -0.01, 0.02, 0.01, -0.01]
    r2 = [0.02, -0.01, 0.04, -0.02, 0.03, -0.01, 0.02, -0.02, 0.01, 0.03]
    r3 = [-0.01, 0.03, -0.01, 0.02, -0.02, 0.01, -0.01, 0.02, -0.01, 0.01]

    cov = _build_cov_matrix([r1, r2, r3])
    assert len(cov) == 3
    assert len(cov[0]) == 3

    # Risk parity
    w_rp = solve_risk_parity(cov)
    assert len(w_rp) == 3
    assert round(sum(w_rp), 2) == 1.0
    assert all(w > 0 for w in w_rp)

    # Min variance
    w_mv = solve_min_variance(cov)
    assert len(w_mv) == 3
    assert round(sum(w_mv), 2) == 1.0

    # Max sharpe
    w_ms = solve_max_sharpe([0.15, 0.25, 0.10], cov)
    assert len(w_ms) == 3
    assert round(sum(w_ms), 2) == 1.0


def test_strategy_evolution_service():
    store = InMemoryStore(load_from_db=False)
    service = StrategyEvolutionService(store)
    evos = service.list_evolutions()
    assert len(evos) >= 1
    assert evos[0]["status"] in ("approved", "ready", "applied")

    # Diagnose and evolve mock
    result = service.diagnose_and_evolve("strat-trend-001")
    assert "evolution_id" in result
    assert "sandbox_results" in result
    assert result["sandbox_results"]["sharpe_improvement_pct"] > 0
