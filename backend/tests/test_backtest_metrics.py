"""Unit and integration test suite for Milestone M2:
- Parquet multi-period historical data import
- Slippage models (fixed, percentage, ATR dynamic)
- Fee models (Maker/Taker rates, funding rate payments)
- Quant financial metrics (CAGR, MDD, Sharpe, Sortino, Calmar, Win Rate, Profit Factor, Payoff Ratio)
- Metrics edge cases and safety guards (zero division, zero volatility, 100% win/loss, bankruptcy)
- Strategy parameter Grid Search Optimizer
"""

import io
import math
from decimal import Decimal
import pandas as pd
import pytest

from app.services.backtest_engine import (
    BacktestEngine,
    BacktestPosition,
    BacktestResult,
    BacktestTrade,
    FeeModel,
    SlippageModel,
)
from app.services.historical_data_service import HistoricalDataService
from app.strategies.base import ParamSpec, Strategy, StrategyMeta
from app.strategies.registry import registry as strategy_registry
from app.strategies.signal import Bar, Signal, SignalType


# ── Fixtures & Helper Strategies ──────────────────────────────────────

class MockTrendStrategy(Strategy):
    meta = StrategyMeta(
        kind="mock_trend",
        name="Mock Trend",
        version="1.0.0",
        params=(
            ParamSpec("fast_period", int, 3),
            ParamSpec("slow_period", int, 8),
            ParamSpec("cash_pct", float, 0.3),
        ),
        warmup_bars=5,
        symbols=("BTCUSDT",),
    )

    def on_bar(self, ctx, bar: Bar) -> list[Signal]:
        fast = ctx.indicator("ema", bar.symbol, count=20, length=self.p["fast_period"])
        slow = ctx.indicator("ema", bar.symbol, count=20, length=self.p["slow_period"])
        if fast is None or slow is None:
            return []
        pos = ctx.position(bar.symbol)
        if pos is None and fast > slow:
            return [Signal(type=SignalType.OPEN_LONG, symbol=bar.symbol, cash_pct=self.p["cash_pct"])]
        elif pos is not None and fast < slow:
            return [Signal(type=SignalType.CLOSE_LONG, symbol=bar.symbol, position_pct=1.0)]
        return []


def generate_synthetic_bars(count: int = 100, base_price: float = 50000.0, trend: float = 10.0, symbol: str = "BTCUSDT") -> list[Bar]:
    bars = []
    base_time = 1700000000000
    price = base_price
    for i in range(count):
        open_time = base_time + i * 3600000
        open_p = price
        # Create small wave oscillation
        wave = math.sin(i * 0.2) * 50.0
        close_p = open_p + trend + wave
        high_p = max(open_p, close_p) + 20.0
        low_p = min(open_p, close_p) - 20.0
        bars.append(Bar(
            symbol=symbol,
            open_time=open_time,
            open=Decimal(str(round(open_p, 2))),
            high=Decimal(str(round(high_p, 2))),
            low=Decimal(str(round(low_p, 2))),
            close=Decimal(str(round(close_p, 2))),
            volume=Decimal("10.5"),
            close_time=open_time + 3599999,
        ))
        price = close_p
    return bars


# ── Test Suite ────────────────────────────────────────────────────────

def test_parquet_import_multi_period():
    """Test HistoricalDataService.import_parquet across multiple timeframes (1m, 5m, 1h, 1d)."""
    service = HistoricalDataService()

    for period, step_ms in [("1m", 60000), ("5m", 300000), ("1h", 3600000), ("1d", 86400000)]:
        df = pd.DataFrame({
            "timestamp": [1700000000000 + i * step_ms for i in range(20)],
            "open": [50000.0 + i for i in range(20)],
            "high": [50010.0 + i for i in range(20)],
            "low": [49990.0 + i for i in range(20)],
            "close": [50005.0 + i for i in range(20)],
            "volume": [1.5 + i * 0.1 for i in range(20)],
        })

        buf = io.BytesIO()
        df.to_parquet(buf, engine="pyarrow")
        buf.seek(0)

        res = service.import_parquet("BTCUSDT", period, buf.getvalue())
        assert res["bars_imported"] == 20
        assert res["symbol"] == "BTCUSDT"
        assert res["period"] == period
        assert res["errors"] == 0
        assert "1700000000000" in res["time_range"]


def test_parquet_import_schema_normalization():
    """Test column alias normalization (ts/vol) and datetime types."""
    service = HistoricalDataService()
    df = pd.DataFrame({
        "ts": [1700000000000, 1700003600000],
        "open": [100.0, 101.0],
        "high": [105.0, 106.0],
        "low": [99.0, 100.0],
        "close": [102.0, 103.0],
        "vol": [50.0, 60.0],
    })
    buf = io.BytesIO()
    df.to_parquet(buf)
    res = service.import_parquet("ETHUSDT", "1h", buf.getvalue())
    assert res["bars_imported"] == 2


def test_slippage_models():
    """Test Fixed, Percentage (BPS), and ATR Dynamic slippage models."""
    bar = Bar("BTCUSDT", 1700000000000, Decimal("50000"), Decimal("50500"), Decimal("49500"), Decimal("50000"), Decimal("10"), 1700003599999)

    # 1. None
    slip_none = SlippageModel.resolve("none")
    assert slip_none.apply("buy", Decimal("50000"), bar) == Decimal("50000")
    assert slip_none.apply("sell", Decimal("50000"), bar) == Decimal("50000")

    # 2. Fixed price
    slip_fixed = SlippageModel.resolve("fixed_price", slippage_price=10)
    assert slip_fixed.apply("buy", Decimal("50000"), bar) == Decimal("50010")
    assert slip_fixed.apply("sell", Decimal("50000"), bar) == Decimal("49990")

    # 3. Percentage / BPS (conservative_1.5bps = 0.00015)
    slip_bps = SlippageModel.resolve("conservative_1.5bps")
    assert slip_bps.apply("buy", Decimal("50000"), bar) == Decimal("50007.50000000")
    assert slip_bps.apply("sell", Decimal("50000"), bar) == Decimal("49992.50000000")

    # 4. ATR Dynamic (Range = 1000, atr_mult = 0.05 -> slip = 50)
    slip_atr = SlippageModel.resolve("atr", atr_mult=0.05)
    assert slip_atr.apply("buy", Decimal("50000"), bar) == Decimal("50050")
    assert slip_atr.apply("sell", Decimal("50000"), bar) == Decimal("49950")


def test_fee_models():
    """Test Maker/Taker rate resolution and perpetual contract funding payments."""
    # 1. Tiered fee resolution
    fee = FeeModel.resolve("maker_0.02pct_taker_0.04pct")
    # Qty 1 BTC @ 50000 -> Maker fee 50000 * 0.0002 = 10.0, Taker fee 50000 * 0.0004 = 20.0
    assert fee.calculate(Decimal("1.0"), Decimal("50000.0"), is_maker=True) == Decimal("10.00000000")
    assert fee.calculate(Decimal("1.0"), Decimal("50000.0"), is_maker=False) == Decimal("20.00000000")

    # 2. Funding rate payment
    # Long pays positive funding: 1.0 BTC @ 50000 * 0.0001 = 5.0
    payment_long = fee.funding_payment(Decimal("1.0"), Decimal("50000.0"), funding_rate=Decimal("0.0001"), is_long=True)
    assert payment_long == Decimal("5.00000000")

    # Short receives positive funding: -5.0
    payment_short = fee.funding_payment(Decimal("1.0"), Decimal("50000.0"), funding_rate=Decimal("0.0001"), is_long=False)
    assert payment_short == Decimal("-5.00000000")


def test_quant_metrics_comprehensive():
    """Test full calculation of CAGR, MDD, Sharpe, Sortino, Calmar, Win Rate, Profit Factor, Payoff Ratio."""
    bars = generate_synthetic_bars(count=120, base_price=50000.0, trend=20.0)
    engine = BacktestEngine(
        bars=bars,
        strategy_cls=MockTrendStrategy,
        params={"fast_period": 3, "slow_period": 8, "cash_pct": 0.3},
        initial_capital="100000.00",
        fee_model="maker_0.02pct_taker_0.04pct",
        slippage_model="conservative_1.5bps",
    )
    result = engine.run()
    assert result.status == "completed"
    m = result.metrics

    # Check presence and types of all required contract fields
    assert "net_profit" in m
    assert "final_equity" in m
    assert "total_return_pct" in m
    assert "cagr" in m
    assert "sharpe_ratio" in m
    assert "sortino_ratio" in m
    assert "calmar_ratio" in m
    assert "max_drawdown" in m
    assert "drawdown_duration" in m
    assert "win_rate" in m
    assert "profit_factor" in m
    assert "payoff_ratio" in m
    assert "total_trades" in m

    assert isinstance(m["cagr"], float)
    assert isinstance(m["sortino_ratio"], float)
    assert isinstance(m["calmar_ratio"], float)
    assert isinstance(m["payoff_ratio"], float)
    assert isinstance(m["drawdown_duration"], int)
    assert "%" in m["max_drawdown"]
    assert "%" in m["win_rate"]


def test_metrics_edge_cases_and_safeguards():
    """Test zero volatility, zero trades, zero drawdown, and bankruptcy boundary protections."""
    bars = generate_synthetic_bars(count=50, base_price=50000.0, trend=0.0)
    engine = BacktestEngine(
        bars=bars,
        strategy_cls=MockTrendStrategy,
        params={"fast_period": 3, "slow_period": 8, "cash_pct": 0.3},
        initial_capital="100000.00",
    )

    # 1. Flat equity curve (zero volatility, no trades)
    flat_equity = [(bars[i].open_time, Decimal("100000.00")) for i in range(50)]
    m_flat = engine._metrics([], flat_equity, Decimal("100000.00"), Decimal("0"))
    assert m_flat["sharpe_ratio"] == "0.00"
    assert m_flat["sortino_ratio"] == 0.0
    assert m_flat["calmar_ratio"] == 0.0
    assert m_flat["win_rate"] == "0.00%"
    assert m_flat["profit_factor"] == "0.00"
    assert m_flat["payoff_ratio"] == 0.0
    assert m_flat["total_trades"] == 0

    # 2. 100% win trades (zero losses) -> Sortino & ProfitFactor safe 999.0
    win_trade = BacktestTrade(
        entry_time=1700000000000, exit_time=1700003600000, symbol="BTCUSDT", side="buy",
        quantity=Decimal("1"), entry_price=Decimal("50000"), exit_price=Decimal("51000"),
        gross_pnl=Decimal("1000"), fee_paid=Decimal("10"), net_pnl=Decimal("990"),
        return_pct=Decimal("0.02"), exit_reason="tp",
    )
    m_win = engine._metrics([win_trade], flat_equity, Decimal("100990.00"), Decimal("0"))
    assert m_win["win_rate"] == "100.00%"
    assert float(m_win["profit_factor"]) >= 999.0
    assert m_win["payoff_ratio"] >= 999.0

    # 3. Bankruptcy / negative equity ($V_N \le 0$) -> CAGR = -1.0 (-100%), MDD = 100%
    bankrupt_equity = [(bars[0].open_time, Decimal("100000")), (bars[1].open_time, Decimal("0"))]
    m_bankrupt = engine._metrics([], bankrupt_equity, Decimal("0"), Decimal("1.0"))
    assert m_bankrupt["cagr"] == -1.0
    assert "-100.0000%" in m_bankrupt["max_drawdown"]


def test_grid_search_optimizer():
    """Test Cartesian grid search optimization over parameter space."""
    bars = generate_synthetic_bars(count=60, base_price=50000.0, trend=15.0)

    param_grid = {
        "fast_period": [2, 3, 5],
        "slow_period": [8, 12],
    }

    opt_result = BacktestEngine.optimize(
        strategy_cls=MockTrendStrategy,
        base_params={"cash_pct": 0.3},
        param_grid=param_grid,
        bars=bars,
        initial_capital="100000.00",
        metric="sharpe_ratio",
        max_runs=20,
    )

    assert opt_result["best_params"] is not None
    assert opt_result["best_metric"] == "sharpe_ratio"
    assert opt_result["best_metric_value"] is not None
    assert opt_result["runs"] == 6  # 3 * 2 combinations
    assert len(opt_result["results"]) == 6
    # Verify sorted order
    results = opt_result["results"]
    for i in range(len(results) - 1):
        assert results[i]["numeric_metric"] >= results[i + 1]["numeric_metric"]
