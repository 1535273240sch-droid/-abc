from typing import Any, Optional
from datetime import datetime

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    strategy_id: str
    strategy_version: str
    data_snapshot: str = "snap_parquet_default"
    fee_model: str = "maker_0.02pct_taker_0.04pct"
    slippage_model: str = "conservative_1.5bps"
    initial_capital: str = "100000.00"
    mode: str = "paper"
    idempotency_key: str | None = None


class BacktestResponse(BaseModel):
    backtest_id: str
    account_id: str
    strategy_id: str
    strategy_version: str
    parameters: dict
    data_snapshot: str
    fee_model: str
    slippage_model: str
    run_environment: str
    initial_capital: str
    mode: str
    status: str
    net_profit: str | None = None
    sharpe_ratio: str | None = None
    max_drawdown: str | None = None
    win_rate: str | None = None
    total_trades: int = 0
    code_ref: str | None = None
    idempotency_key: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class BacktestOptimizeRequest(BaseModel):
    strategy_id: str
    strategy_version: str
    param_grid: dict[str, list[Any]]
    data_snapshot: str = "snap_parquet_default"
    fee_model: str = "maker_0.02pct_taker_0.04pct"
    slippage_model: str = "conservative_1.5bps"
    initial_capital: str = "100000.00"
    metric: str = "sharpe_ratio"
    max_runs: int = Field(default=50, ge=1, le=200)


class BacktestOptimizeResponse(BaseModel):
    best_params: dict[str, Any] | None = None
    best_metric: str
    best_metric_value: str | None = None
    runs: int
    best_result: BacktestResponse | None = None


class HistoricalImportBinanceRequest(BaseModel):
    symbol: str
    period: str = "1h"
    start_ms: int
    end_ms: int


class HistoricalImportCsvRequest(BaseModel):
    symbol: str
    period: str = "1h"
    csv_text: str
    delimiter: str = ","


class HistoricalSeriesResponse(BaseModel):
    symbol: str
    period: str
    bars: int
