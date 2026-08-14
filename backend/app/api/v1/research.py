from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import get_audit_service, get_backtest_service, get_historical_data_service
from app.schemas.research import (
    BacktestOptimizeRequest,
    BacktestOptimizeResponse,
    BacktestRequest,
    BacktestResponse,
    HistoricalImportBinanceRequest,
    HistoricalImportCsvRequest,
    HistoricalSeriesResponse,
)
from app.services.audit_service import AuditService
from app.services.backtest_service import BacktestService
from app.services.historical_data_service import HistoricalDataService

router = APIRouter(prefix="/api/v1/research", tags=["Research"])


@router.post("/backtests", response_model=BacktestResponse, status_code=201)
async def create_backtest(
    body: BacktestRequest,
    request: Request,
    backtest_service: BacktestService = Depends(get_backtest_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    bt = backtest_service.execute(
        strategy_id=body.strategy_id,
        strategy_version=body.strategy_version,
        data_snapshot=body.data_snapshot,
        fee_model=body.fee_model,
        slippage_model=body.slippage_model,
        initial_capital=body.initial_capital,
        mode=body.mode,
        idempotency_key=body.idempotency_key,
    )

    trace_id = getattr(request.state, "request_id", None)
    audit_service.record(
        event_type="backtest.completed",
        actor=bt.account_id,
        resource_type="backtest",
        resource_id=bt.backtest_id,
        details={
            "strategy_id": bt.strategy_id,
            "strategy_version": bt.strategy_version,
            "net_profit": bt.net_profit,
            "sharpe_ratio": bt.sharpe_ratio,
            "total_trades": bt.total_trades,
            "data_snapshot": bt.data_snapshot,
        },
        ip_address=request.client.host if request.client else None,
        trace_id=trace_id,
    )

    return BacktestResponse(
        backtest_id=bt.backtest_id,
        account_id=bt.account_id,
        strategy_id=bt.strategy_id,
        strategy_version=bt.strategy_version,
        parameters=bt.parameters,
        data_snapshot=bt.data_snapshot,
        fee_model=bt.fee_model,
        slippage_model=bt.slippage_model,
        run_environment=bt.run_environment,
        initial_capital=bt.initial_capital,
        mode=bt.mode.value,
        status=bt.status.value,
        net_profit=bt.net_profit,
        sharpe_ratio=bt.sharpe_ratio,
        max_drawdown=bt.max_drawdown,
        win_rate=bt.win_rate,
        total_trades=bt.total_trades,
        idempotency_key=bt.idempotency_key,
        code_ref=bt.code_ref,
        created_at=bt.created_at,
        completed_at=bt.completed_at,
    )


@router.get("/backtests", response_model=list[BacktestResponse])
async def list_backtests(
    account_id: str | None = Query(None),
    backtest_service: BacktestService = Depends(get_backtest_service),
):
    bts = backtest_service.list_backtests(account_id=account_id)
    return [
        BacktestResponse(
            backtest_id=b.backtest_id,
            account_id=b.account_id,
            strategy_id=b.strategy_id,
            strategy_version=b.strategy_version,
            parameters=b.parameters,
            data_snapshot=b.data_snapshot,
            fee_model=b.fee_model,
            slippage_model=b.slippage_model,
            run_environment=b.run_environment,
            initial_capital=b.initial_capital,
            mode=b.mode.value,
            status=b.status.value,
            net_profit=b.net_profit,
            sharpe_ratio=b.sharpe_ratio,
            max_drawdown=b.max_drawdown,
            win_rate=b.win_rate,
            total_trades=b.total_trades,
            idempotency_key=b.idempotency_key,
            code_ref=b.code_ref,
            created_at=b.created_at,
            completed_at=b.completed_at,
        )
        for b in bts
    ]


@router.get("/backtests/{backtest_id}", response_model=BacktestResponse)
async def get_backtest(
    backtest_id: str,
    backtest_service: BacktestService = Depends(get_backtest_service),
):
    bt = backtest_service.get_backtest(backtest_id)
    if not bt:
        from app.core.errors import QuantError
        raise QuantError("NOT_FOUND", f"Backtest {backtest_id} not found", status_code=404)
    return BacktestResponse(
        backtest_id=bt.backtest_id,
        account_id=bt.account_id,
        strategy_id=bt.strategy_id,
        strategy_version=bt.strategy_version,
        parameters=bt.parameters,
        data_snapshot=bt.data_snapshot,
        fee_model=bt.fee_model,
        slippage_model=bt.slippage_model,
        run_environment=bt.run_environment,
        initial_capital=bt.initial_capital,
        mode=bt.mode.value,
        status=bt.status.value,
        net_profit=bt.net_profit,
        sharpe_ratio=bt.sharpe_ratio,
        max_drawdown=bt.max_drawdown,
        win_rate=bt.win_rate,
        total_trades=bt.total_trades,
        idempotency_key=bt.idempotency_key,
        code_ref=bt.code_ref,
        created_at=bt.created_at,
        completed_at=bt.completed_at,
    )


@router.post("/backtests/optimize", response_model=BacktestOptimizeResponse)
async def optimize_backtest(
    body: BacktestOptimizeRequest,
    request: Request,
    backtest_service: BacktestService = Depends(get_backtest_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    from app.services.backtest_engine import BacktestEngine

    strategy = backtest_service._store.strategies.get(body.strategy_id)
    if not strategy:
        from app.core.errors import QuantError
        raise QuantError("NOT_FOUND", f"Strategy {body.strategy_id} not found", status_code=404)

    bars = backtest_service._bars_for_snapshot(body.data_snapshot, getattr(strategy, "symbols", None) or ("BTCUSDT",))
    result = BacktestEngine.optimize(
        strategy_cls=backtest_service._store.strategy_engines.get(strategy.kind) or BacktestEngine,
        base_params=strategy.parameters,
        param_grid=body.param_grid,
        bars=bars,
        initial_capital=body.initial_capital,
        fee_model=body.fee_model,
        slippage_model=body.slippage_model,
        metric=body.metric,
        max_runs=body.max_runs,
    )

    audit_service.record(
        event_type="backtest.optimized",
        actor="system",
        resource_type="backtest",
        resource_id=strategy.strategy_id,
        details={"runs": result["runs"], "metric": body.metric},
        ip_address=request.client.host if request.client else None,
        trace_id=getattr(request.state, "request_id", None),
    )

    best = result.get("best_result")
    return BacktestOptimizeResponse(
        best_params=result.get("best_params"),
        best_metric=result.get("best_metric"),
        best_metric_value=result.get("best_metric_value"),
        runs=result.get("runs", 0),
        best_result=BacktestResponse(
            backtest_id="opt",
            account_id="paper-main",
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.version,
            parameters=result.get("best_params") or {},
            data_snapshot=body.data_snapshot,
            fee_model=body.fee_model,
            slippage_model=body.slippage_model,
            run_environment="backtest-optimizer",
            initial_capital=body.initial_capital,
            mode="paper",
            status="completed",
            net_profit=best.net_profit if best else None,
            sharpe_ratio=best.sharpe_ratio if best else None,
            max_drawdown=best.max_drawdown if best else None,
            win_rate=best.win_rate if best else None,
            total_trades=best.total_trades if best else 0,
            created_at=strategy.created_at,
        ) if best else None,
    )


@router.post("/historical/import/binance", response_model=dict)
async def import_binance(
    body: HistoricalImportBinanceRequest,
    request: Request,
    service: HistoricalDataService = Depends(get_historical_data_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    result = service.import_binance(
        symbol=body.symbol,
        period=body.period,
        start_ms=body.start_ms,
        end_ms=body.end_ms,
    )
    audit_service.record("historical.imported", "system", "historical", body.symbol, result, request.client.host if request.client else None, getattr(request.state, "request_id", None))
    return result


@router.post("/historical/import/csv", response_model=dict)
async def import_csv(
    body: HistoricalImportCsvRequest,
    request: Request,
    service: HistoricalDataService = Depends(get_historical_data_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    result = service.import_csv(symbol=body.symbol, period=body.period, csv_text=body.csv_text, delimiter=body.delimiter)
    audit_service.record("historical.csv_imported", "system", "historical", body.symbol, result, request.client.host if request.client else None, getattr(request.state, "request_id", None))
    return result


@router.get("/historical/series", response_model=list[HistoricalSeriesResponse])
async def list_historical_series(service: HistoricalDataService = Depends(get_historical_data_service)):
    out = []
    for item in service.list_series():
        out.append(HistoricalSeriesResponse(symbol=item.get("symbol"), period=item.get("period"), bars=item.get("bars", 0)))
    return out


@router.delete("/historical/series")
async def delete_historical_series(symbol: str, period: str, service: HistoricalDataService = Depends(get_historical_data_service)):
    return service.delete_series(symbol=symbol, period=period)
