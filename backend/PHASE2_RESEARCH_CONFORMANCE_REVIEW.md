# Phase 2: Research Closed-Loop — Conformance Review

> Generated: 2026-08-09
> Source: `ARCHITECTURE.md` sections 4.2, 5, 6, 9, 11
> Scope: `backend/` only
> Mode: **paper / simulation only** — no real network, no real keys, no live trading, no production deployment

---

## 1. Implemented

### Versioned Strategy Lifecycle

| Endpoint | Method | Status | Description |
|---|---|---|---|
| `GET /api/v1/strategies` | GET | 200 | List all strategies (with code_ref, owner, kind) |
| `POST /api/v1/strategies` | POST | 201 | Create new strategy (ID unique → 409 CONFLICT) |
| `GET /api/v1/strategies/{strategy_id}` | GET | 200 | Get single strategy (404 if missing) |
| `PATCH /api/v1/strategies/{strategy_id}` | PATCH | 200 | Update version, code_ref, parameters, etc. (404 if missing) |

**`Strategy` domain model** (`app/models/domain.py`):
- `strategy_id`, `name`, `version`, `description`, `parameters`
- `code_ref` — git/hash reference for strategy code (ARCHITECTURE.md §4.2)
- `owner`, `kind` — responsibility tracking
- `status`, `created_at`, `updated_at`

**`StrategyService`** (`app/services/strategy_service.py`):
- `create()` — ID uniqueness check, full field validation
- `get()` — single lookup
- `update()` — patch semantics, preserves unset fields
- `get_strategies()` — list all

### Deterministic Paper Backtest (traceable metrics)

| Endpoint | Method | Status | Description |
|---|---|---|---|
| `POST /api/v1/research/backtests` | POST | 201 | Execute deterministic backtest (paper-only) |
| `GET /api/v1/research/backtests` | GET | 200 | List backtests |
| `GET /api/v1/research/backtests/{id}` | GET | 200 | Get single backtest result |

**`Backtest` domain model** — traceable fields:
- `strategy_id`, `strategy_version`, `parameters` (snapshot at execution time)
- `code_ref` — copied from strategy at execution time for traceability
- `data_snapshot`, `fee_model`, `slippage_model`, `run_environment`
- `initial_capital`, `net_profit`, `sharpe_ratio`, `max_drawdown`, `win_rate`, `total_trades`
- `idempotency_key` (dedup), `created_at`, `completed_at`

**Deterministic simulation**: SHA-256 hash of `(strategy_id, version, data_snapshot, fee_model, slippage_model)` → reproducible metrics per input set.

### Integration with Existing Infrastructure

| Existing | Integration |
|---|---|
| `AuditService` | `strategy.created`, `strategy.updated`, `backtest.completed` events |
| Event bus | `research.backtest_completed.v1` |
| `X-Request-ID` / trace_id | Propagated through all audit events |
| Paper-only guard | 403 `LIVE_TRADING_NOT_ALLOWED` at backtest boundary |
| Idempotency | `idempotency_key` dedup for backtests; `strategy_id` uniqueness for creation |
| Decimal semantics | All monetary metrics as `Decimal` strings |
| Unified error format | `CONFLICT`(409), `NOT_FOUND`(404), `INVALID_STRATEGY_VERSION`(400) |

---

## 2. Test Evidence

**10 new tests** (129 total, all passing):

| Test | Verifies |
|---|---|
| `test_strategy_create` | Full POST with code_ref, owner, kind |
| `test_strategy_create_conflict` | 409 CONFLICT for duplicate strategy_id |
| `test_strategy_get` | code_ref present in response |
| `test_strategy_get_not_found` | 404 |
| `test_strategy_update_version` | PATCH with version + code_ref |
| `test_strategy_update_not_found` | 404 |
| `test_strategy_list_has_code_ref` | code_ref in list response |
| `test_strategy_audit_event` | `strategy.created` audit event |
| `test_backtest_includes_code_ref` | code_ref propagated from strategy → backtest |
| `test_backtest_traceable_fields` | Full traceable field set validated |

---

## 3. Verification Summary

| Check | Result |
|---|---|
| `pytest` (129 tests) | 129 passed, 0 failed |
| `compileall` | All modules clean |
| `uvicorn` smoke test | `/health` 200, `/api/v1/system/status` 200, `GET /api/v1/strategies/trend-btc` 200 (`code_ref=git:.../trend_btc_v100.py`, `owner=Research Team A`), `POST /api/v1/research/backtests` 201 (`code_ref=git:.../trend_btc_v100.py`, `sharpe=1.8`, `trades=353`) |

---

## 4. Explicitly NOT Implemented (Real Research / Production)

- **Real backtest engine**: Current simulation is hash-based; no real OHLCV/K-line engine.
- **Parquet/object storage**: `data_snapshot` is a string identifier; no actual storage layer.
- **Factor registry**: No standalone factor/data-feature pipeline.
- **Equity curve storage**: Not stored in current model (frontend research page uses mock).
- **Strategy code execution**: `code_ref` is a string reference; no actual code execution environment.
- **Authentication / RBAC**: No login, JWT, or permission enforcement.
- **Persistence**: In-memory only; no PostgreSQL/Redis/ClickHouse.
- **Live trading**: Structurally blocked by paper-only guards.
- **Backtest comparison / multi-run analytics**: No cross-run comparison or aggregate metrics.