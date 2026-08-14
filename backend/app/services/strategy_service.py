import uuid
from typing import Any

from app.core.errors import QuantError
from app.models.domain import Strategy, utcnow


class StrategyService:
    def __init__(self, store: Any):
        self._store = store
        self._seed()

    def _seed(self):
        strategies = [
            Strategy("trend-btc", "BTC Trend Following", "1.0.0", "Medium-frequency trend following strategy for BTCUSDT", {"ema_fast": 20, "ema_slow": 50}, code_ref="git:quant-repo/strategies/trend_btc_v100.py", owner="Research Team A", kind="trend"),
            Strategy("arb-eth", "ETH Arbitrage", "1.0.0", "Cross-exchange arbitrage for ETH pairs", {"min_spread": "0.001"}, code_ref="git:quant-repo/strategies/arb_eth_v100.py", owner="Research Team B", kind="arbitrage"),
            Strategy("grid-bnb", "BNB Grid Trading", "1.0.0", "Grid trading strategy for BNBUSDT", {"grid_levels": 10, "spread": "0.005"}, code_ref="git:quant-repo/strategies/grid_bnb_v100.py", owner="Research Team A", kind="grid"),
        ]
        for s in strategies:
            self._store.strategies[s.strategy_id] = s

    def create(
        self,
        strategy_id: str,
        name: str,
        version: str,
        description: str,
        parameters: dict | None = None,
        code_ref: str | None = None,
        owner: str | None = None,
        kind: str | None = None,
    ) -> Strategy:
        if strategy_id in self._store.strategies:
            raise QuantError("CONFLICT", f"Strategy {strategy_id} already exists", status_code=409)
        strategy = Strategy(
            strategy_id=strategy_id,
            name=name,
            version=version,
            description=description,
            parameters=parameters,
            code_ref=code_ref,
            owner=owner,
            kind=kind,
        )
        with self._store.get_lock():
            self._store.strategies[strategy_id] = strategy
        return strategy

    def get(self, strategy_id: str) -> Strategy | None:
        return self._store.strategies.get(strategy_id)

    def update(
        self,
        strategy_id: str,
        name: str | None = None,
        version: str | None = None,
        description: str | None = None,
        parameters: dict | None = None,
        code_ref: str | None = None,
        owner: str | None = None,
        kind: str | None = None,
        status: str | None = None,
    ) -> Strategy:
        strategy = self._store.strategies.get(strategy_id)
        if not strategy:
            raise QuantError("NOT_FOUND", f"Strategy {strategy_id} not found", status_code=404)
        with self._store.get_lock():
            if name is not None:
                strategy.name = name
            if version is not None:
                strategy.version = version
            if description is not None:
                strategy.description = description
            if parameters is not None:
                strategy.parameters = parameters
            if code_ref is not None:
                strategy.code_ref = code_ref
            if owner is not None:
                strategy.owner = owner
            if kind is not None:
                strategy.kind = kind
            if status is not None:
                strategy.status = status
            strategy.updated_at = utcnow()
        return strategy

    def get_strategies(self) -> list[Strategy]:
        return list(self._store.strategies.values())