# Phase 3: Portfolio Target — Conformance Review

> Generated: 2026-08-09
> Source: `ARCHITECTURE.md` §4.3 (Signal → Portfolio Target → Risk Preflight → Order Intent)
> Scope: `backend/` only
> Mode: **paper / simulation only** — no real network, no real keys, no live trading, no production deployment

---

## 1. Implemented

### Portfolio Target API

| Endpoint | Method | Status | Description |
|---|---|---|---|
| `POST /api/v1/portfolio/targets` | POST | 201 | Create a portfolio target (paper-only, no order creation) |
| `GET /api/v1/portfolio/targets` | GET | 200 | List all targets |
| `GET /api/v1/portfolio/targets/{target_id}` | GET | 200 | Get single target (404 if missing) |

### Domain Model — `PortfolioTarget`

| Field | Type | Description |
|---|---|---|
| `target_id` | str | UUID-based unique identifier |
| `account_id` | str | Target account |
| `strategy_id` | str | Source strategy |
| `strategy_version` | str | Strategy version at target time |
| `symbol` | str | Trading symbol |
| `target_quantity` | str | Desired quantity (Decimal) |
| `current_quantity` | str | Current position quantity (computed from `PositionService`) |
| `delta` | str | `target_quantity - current_quantity` (Decimal, computed) |
| `target_weight` | str\|None | Optional weight target |
| `mode` | TradeMode | Always `paper` |
| `idempotency_key` | str\|None | Dedup key |
| `created_at` / `updated_at` | datetime | UTC timestamps |

### Service — `PortfolioTargetService`

- `set_target()` — computes delta from current position, stores target, publishes event
- `get_target()` — single lookup
- `list_targets()` — list with account filter
- Paper-only guard: `LIVE_TRADING_NOT_ALLOWED` (403)
- Idempotency: `idempotency_key` dedup

### Key Safety Boundaries

| Guard | Enforcement |
|---|---|
| No order creation | Portfolio target endpoint does NOT create orders; verified by `test_portfolio_target_no_order_creation` |
| No risk preflight bypass | No order creation path → no risk bypass possible |
| No live trading | `_assert_paper_only()` → 403 `LIVE_TRADING_NOT_ALLOWED` |
| Decimal semantics | `_validate_quantity()` uses `Decimal`; `delta` computed via `Decimal` |
| Audit events | `portfolio.target_created` audit event recorded |
| Versioned events | `portfolio.target_created.v1` published |
| `trace_id` | Propagated through audit events |

### Modified Files

| File | Change |
|---|---|
| `app/models/domain.py` | Added `PortfolioTarget` model (with `delta` computation) |
| `app/models/enums.py` | Added `PORTFOLIO_TARGET_CREATED` audit event type |
| `app/services/portfolio_service.py` | **New** — `PortfolioTargetService` with set/get/list |
| `app/schemas/portfolio.py` | **New** — `PortfolioTargetRequest`/`Response` |
| `app/api/v1/portfolio.py` | **New** — 3 endpoints (POST/GET list/GET by id) |
| `app/core/dependencies.py` | Added `get_portfolio_target_service()` |
| `app/db/memory.py` | Added `portfolio_targets` storage + `portfolio_target_service` |
| `app/main.py` | Registered `portfolio.router` |
| `tests/test_api.py` | Added 11 portfolio target tests |

---

## 2. Test Evidence

**11 new tests** (140 total, all passing):

| Test | Verifies |
|---|---|
| `test_portfolio_target_create` | 201 with target_quantity, current_quantity, delta, mode, target_id |
| `test_portfolio_target_create_with_idempotency` | Same `idempotency_key` → same `target_id` |
| `test_portfolio_target_get` | GET by id returns 200 |
| `test_portfolio_target_get_not_found` | 404 |
| `test_portfolio_target_list` | GET list returns 200 with array |
| `test_portfolio_target_live_mode_blocked` | 403 `LIVE_TRADING_NOT_ALLOWED` |
| `test_portfolio_target_invalid_quantity` | 400 for non-decimal quantity |
| `test_portfolio_target_audit_event` | `portfolio.target_created` audit event |
| `test_portfolio_target_event_bus` | `portfolio.target_created.v1` versioned event |
| `test_portfolio_target_trace_id` | trace_id propagated through audit |
| `test_portfolio_target_no_order_creation` | `/api/v1/orders` returns empty after target creation |

---

## 3. Verification Summary

| Check | Result |
|---|---|
| `pytest` (140 tests) | 140 passed, 0 failed |
| `compileall` | All modules clean |
| `uvicorn` smoke test | `/health` 200, `/api/v1/system/status` 200 |
| | `POST /api/v1/portfolio/targets` (paper) → **201** `target=0.75000000 current=0.50000000 delta=0.25000000` |
| | `POST /api/v1/portfolio/targets` (live) → **403** `LIVE_TRADING_NOT_ALLOWED` |

---

## 4. Explicitly NOT Implemented (Real Portfolio / Production)

- **No order creation**: Portfolio target is a pure signal endpoint; order creation requires `POST /api/v1/orders/intents` + risk preflight.
- **No risk preflight bypass**: The target endpoint does not create orders or bypass risk.
- **No real exchange connection**: Adapter layer is not consumed by portfolio target.
- **No real API keys / secrets**: Not present anywhere.
- **No authentication / RBAC**: No login, JWT, or permission enforcement.
- **No persistence**: In-memory only; no PostgreSQL/Redis/ClickHouse.
- **No live trading**: Structurally blocked by paper-only guard.
- **No automatic order generation**: Signal → Target is implemented; Target → Order is a manual/separate step.