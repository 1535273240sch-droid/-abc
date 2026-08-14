# Architecture Conformance Review

> Generated: 2026-08-09
> Source: `ARCHITECTURE.md` sections 3-11
> Scope: `backend/` only

---

## 1. Implemented (Phase 1 / Paper Closed-Loop)

### Section 3 — Module Boundaries & Responsibilities

| Module | Status | Notes |
|---|---|---|
| `market_data` | ✅ Partial | `MarketService` with seeded symbols/tickers; no WebSocket or exchange adapter |
| `risk` | ✅ Implemented | `RiskService.preflight()` with Decimal arithmetic, rule checks, state machine |
| `execution` | ✅ Implemented | `OrderService.create_intent()` with order state machine, idempotency, risk decision binding |
| `portfolio` | ✅ Partial | `PositionService` with seed positions; no real target-calc or PnL reconciliation |
| `control` | 🔲 Not started | User/RBAC/approvals/API key management — Phase 2+ |
| `research` | 🔲 Not started | Factor/backtest/strategy version management — Phase 2 |
| `adapters` | 🔲 Not started | Exchange adapter layer — Phase 4 |
| `agent_orchestrator` | 🔲 Not started | Agent task/tool/approval system — Phase 3 |
| `console` | 🔲 Frontend | Backend API contract ready; frontend mostly mock (see `FINAL_INTEGRATION_REVIEW.md`) |
| `observability` | ✅ Partial | `X-Request-ID` propagation, structured audit events, error `trace_id` |

### Section 4 — Key Business Flows

**4.1 Market Data Flow** — `MarketService` provides seeded tickers/symbols. No exchange adapter or WebSocket. No data quality module.

**4.3 Trading Flow (Paper Closed Loop)** — Fully implemented:

```
Signal → Risk Preflight → Order Intent → Paper Execution → Fill → Position
```

- `POST /api/v1/risk/preflight` → returns `decision_id` (approved/rejected)
- `POST /api/v1/orders/intents` → requires `risk_decision_id`; fails without match
- Paper mode auto-fills orders (status=`new`, `filled_quantity=quantity`)
- Audit events recorded at each step

**4.4 Agent Collaboration Flow** — Not implemented (backend-side). Frontend Agents page uses mock data.

### Section 5 — Technical Baseline

| Requirement | Status |
|---|---|
| Python 3.12 | ✅ |
| FastAPI | ✅ |
| Pydantic v2 | ✅ |
| SQLAlchemy 2 | 🔲 Not needed Phase 1 (in-memory store) |
| Alembic | 🔲 Not needed Phase 1 |
| PostgreSQL | 🔲 Phase 2+ |
| ClickHouse | 🔲 Phase 2+ |
| Redis | 🔲 Phase 2+ |
| Versioned Event Bus | ✅ Implemented (`app/events/bus.py`: `DomainEvent`, `event_type()`, `EventBus.publish/subscribe`) |
| Parquet/object storage | 🔲 Phase 2+ |
| Decimal semantics | ✅ (`_parse_decimal` in `risk_service.py`; all monetary values as strings) |
| Structured logging | ✅ (middleware adds `X-Request-ID`, `X-Process-Time`) |
| Health check | ✅ (`GET /health`, `GET /ready`) |
| Request ID | ✅ (middleware propagates `X-Request-ID`; appears in error responses and audit events) |
| Event ID | ✅ (Audit events and DomainEvents) |
| Audit trail | ✅ (AuditService records all risk preflight and order creation events) |

### Section 6 — Core Data Contracts

| Contract | Status |
|---|---|
| Standard ticker (6.1) | ✅ `TickerResponse` aligned |
| Risk preflight (6.2) | ✅ `PreflightRequest`/`PreflightResponse` aligned |
| Order intent (6.3) | ✅ `OrderIntentRequest`/`OrderResponse` aligned |
| Required API endpoints (6.4) | ✅ All 11 endpoints implemented |
| UTC ISO 8601 timestamps | ✅ |
| String/Decimal monetary values | ✅ (no binary float for price/quantity) |

### Section 7 — Security & Unbypassable Rules

| Rule | Status |
|---|---|
| Default `paper`, no default `live` | ✅ `mode=paper` in `Settings`; order service rejects `live` with `LIVE_TRADING_NOT_ALLOWED` (403) |
| API Key only via Secret Manager | ✅ No keys in code or config |
| Risk preflight required for orders | ✅ `risk_decision_id` must exist and be `approved` |
| Risk service not bypassable by frontend | ✅ Guard in `OrderService.create_intent()` checks decision before creating order |
| Order state changes auditable | ✅ Audit events recorded on order creation |
| Retry must be idempotent | ✅ `client_order_id` idempotency; `IDEMPOTENCY_CONFLICT` (409) on field mismatch |
| No live switch without approval | ✅ `LIVE_TRADING_NOT_ALLOWED` guard at service boundary |

### Section 9 — Development Phases

| Phase | Status |
|---|---|
| Phase 0: Architecture & baseline | ✅ |
| **Phase 1: Control & data skeleton** | **✅ Complete** |
| Phase 2: Research closed-loop | 🔲 |
| Phase 3: Paper trading closed-loop | ✅ (execution, risk, positions, audit) |
| Phase 4: Exchange adapter & production | 🔲 |

### Section 11 — Acceptance Criteria

| Criterion | Status |
|---|---|
| Architecture boundaries intact | ✅ |
| Backend starts, health/core APIs available | ✅ |
| Order state machine, risk preflight, paper mode tests pass | ✅ (37 tests) |
| All models have idempotency, audit, error response | ✅ |
| No hardcoded keys, no default live, no bypass path | ✅ Verified |
| Decimal, idempotency, risk decision binding, unified error format | ✅ |

---

## 2. Not Yet Implemented (Deferred to Phase 2/3/4)

### Phase 2 (Research Closed-Loop)
- Strategy version management: backtest execution, factor registry, data snapshot
- Performance metrics (Sharpe, max drawdown, win rate)
- Parquet/object storage interface
- `GET /api/v1/strategies` currently returns only seed data
- `POST /api/v1/research/backtest` not implemented

### Phase 3 (Full Paper Trading)
- Signal → Portfolio Target calculation
- Order lifecycle beyond creation: fill simulation, partial fills, cancellations
- PnL reconciliation service
- Position tracking with PnL updates
- Agent orchestrator endpoints

### Phase 4 (Exchange & Production)
- `adapters/` module: Binance/OKX/Bybit REST + WebSocket
- Real connection management, reconnection, rate limiting
- Live order routing to exchange
- Kill switch: `POST /api/v1/system/kill-switch`
- Approvals: `POST /api/v1/approvals`
- PostgreSQL + Alembic migrations
- Redis caching
- ClickHouse for time-series

### Cross-Cutting (Ongoing)
- `control` module: user/RBAC/API key management
- `observability` module: OpenTelemetry, Prometheus, structured logging
- `agent_orchestrator` module: Agent task management, tool permissions, evidence chain
- Authentication: `GET /api/v1/auth/login`, JWT, role-based access
- Exchange connection management: `GET /api/v1/connections`
- System configuration: `GET /api/v1/system/settings`

---

## 3. Verification Summary

| Check | Result |
|---|---|
| `pytest` (37 tests) | 37 passed, 0 failed |
| `compileall` | All modules clean |
| `uvicorn` smoke test | `/health` 200, `/api/v1/system/status` 200 |

## 4. Known Gaps

- In-memory storage only; data lost on restart (Phase 1 acceptable per ARCHITECTURE.md 6.4)
- No real exchange adapter (Phase 4)
- No PostgreSQL/Redis/ClickHouse (Phase 2+)
- No authentication (Phase 2+)
- `live` mode structurally blocked; no approval path exists yet (Phase 3+)