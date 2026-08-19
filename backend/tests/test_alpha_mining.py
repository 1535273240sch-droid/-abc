import pytest
from app.services.alpha_mining_service import (
    FormulaNode,
    evaluate_factor_metrics,
    GeneticAlphaMiner,
    AlphaMiningService,
)
from app.db.memory import InMemoryStore


def test_formula_node_evaluation():
    data = {
        "open": [10.0, 11.0, 12.0, 11.5, 13.0],
        "close": [10.5, 11.2, 11.8, 12.0, 13.5],
        "volume": [100.0, 150.0, 200.0, 180.0, 220.0],
    }
    # ts_delta(close, 1)
    node = FormulaNode(op="ts_delta", window=1, children=[FormulaNode(feature="close")])
    result = node.evaluate(data)
    assert len(result) == 5
    assert result[0] == 0.0
    assert round(result[1], 2) == 0.7


def test_evaluate_factor_metrics():
    factor = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    prices = [10.0, 10.5, 11.0, 11.5, 12.0, 12.5, 13.0, 13.5, 14.0, 14.5, 15.0, 15.5, 16.0, 16.5, 17.0]
    metrics = evaluate_factor_metrics(factor, prices, forward_periods=1)
    assert "rank_ic" in metrics
    assert "ic_ir" in metrics
    assert abs(metrics["rank_ic"]) > 0.8  # highly correlated


def test_genetic_miner_runs():
    data = {
        "open": [100.0 + i * 0.5 for i in range(40)],
        "high": [101.0 + i * 0.5 for i in range(40)],
        "low": [99.0 + i * 0.5 for i in range(40)],
        "close": [100.5 + i * 0.5 for i in range(40)],
        "volume": [1000.0 + (i % 5) * 50 for i in range(40)],
    }
    miner = GeneticAlphaMiner(population_size=10, generations=2)
    factors = miner.mine(data, target_symbol="BTCUSDT")
    assert isinstance(factors, list)


def test_alpha_mining_service_seed_and_list():
    store = InMemoryStore(load_from_db=False)
    service = AlphaMiningService(store)
    factors = service.list_factors()
    assert len(factors) >= 4
    assert factors[0]["symbol"] in ("BTCUSDT", "ETHUSDT", "SOLUSDT")
