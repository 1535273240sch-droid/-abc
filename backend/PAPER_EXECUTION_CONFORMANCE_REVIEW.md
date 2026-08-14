# Paper Execution Closed-Loop — Phase 3 Conformance Review

> Generated: 2026-08-09
> Source: `ARCHITECTURE.md` sections 4, 7, 9, 11
> Scope: `backend/` only

---

## 1. Implemented (Phase 3 — Paper Execution Closed-Loop)

### Order State Machine — `app/services/order_execution_service.py`

Strict state transitions enforced by `_ALLOWED_TRANSITIONS`:

```
NEW → PARTIALLY_FILLED → FILLED
NEW → FILLED
NEW → CANCELLED
NEW → REJECTED
PARTIALLY_FILLED → FILLED
PARTIALLY_FILLED → CANCELLED
```

Any disallowed transition → `INVALID_STATE_TRANSITION` (400). States `FILLED`, `CANCELLED`, `REJECTED`, `PENDING`, `RISK_REJECTED` are terminal.

### Fill Execution — `POST /api/v1/execution/fills`

- Validates order exists, mode is paper, fill quantity does not exceed remaining
- Updates: `filled_quantity` (weighted average), `average_price`, `status`
- Creates `FillRecord` for audit trail
- Publishes `order.filled.v1` domain event
- Updates position via `PositionService.update_on_fill()`

### Cancel / Reject — `POST /api/v1/execution/orders/{id}/cancel`, `POST /api/v1/execution/orders/{id}/reject`

- Validates state transition is allowed
- Publishes `order.cancelled.v1` / `order.rejected.v1` events
- Audits `order.status_changed` event

### Position & PnL Updates — `app/services/position_service.py`

| Operation | Behavior |
|---|---|
| Buy fill | Increases position quantity; weighted-average entry price |
| Sell fill | Decreases position quantity; realizes PnL = (fill_price - entry_price) × fill_qty |
| New position | Auto-created if none exists for account/symbol/side |
| Event | Publishes `position.updated.v1` |

### Reconciliation Service — `app/services/reconciliation_service.py`

- `POST /api/v1/execution/reconciliation` — runs check comparing total position quantity vs total order filled quantity
- Reports `consistent` or `discrepancy` with detailed summary
- Publishes `reconciliation.completed.v1`
- `GET /api/v1/execution/reconciliation` — lists all reconciliation logs

### New API Endpoints

| Endpoint | Method | Status | Description |
|---|---|---|---|
| `POST /api/v1/execution/fills` | POST | 200 | Record a fill (partial or full) |
| `POST /api/v1/execution/orders/{id}/cancel` | POST | 200 | Cancel an order |
| `POST /api/v1/execution/orders/{id}/reject` | POST | 200 | Reject an order |
| `POST /api/v1/execution/reconciliation` | POST | 200 | Run reconciliation |
| `GET /api/v1/execution/reconciliation` | GET | 200 | List reconciliation logs |

### New Domain Models

| Model | Fields |
|---|---|
| `FillRecord` | fill_id, client_order_id, account_id, symbol, side, fill_quantity, fill_price, trade_mode, created_at |
| `ReconciliationLog` | reconciliation_id, account_id, status, details, summary, created_at |

### New Enums

| Enum | Values |
|---|---|
| `ReconciliationStatus` | consistent, discrepancy |
| `AuditEventType` | +`ORDER_FILLED`, `POSITION_PNL_UPDATED`, `RECONCILIATION` |

### Integration with Existing Infrastructure

| Existing | Integration |
|---|---|
| `OrderService.create_intent()` | Changed: no longer auto-fills paper orders; starts as NEW |
| `RiskService` | `risk_decision_id` still required for order creation |
| `AuditService` | `order.filled`, `order.status_changed`, `reconciliation.ran` events |
| Event bus | `order.filled.v1`, `order.cancelled.v1`, `order.rejected.v1`, `position.updated.v1`, `reconciliation.completed.v1` |
| X-Request-ID / trace_id | Propagated through all audit events |
| Paper-only guard | At execution service boundary — 403 `LIVE_TRADING_NOT_ALLOWED` |
| Decimal semantics | All fill quantities, prices, PnL use `Decimal`; weighted-average price calculation |
| Unified error format | `INVALID_STATE_TRANSITION`, `INVALID_FILL`, `VALIDATION_ERROR` |

---

## 2. ARCHITECTURE.md Section Conformance

### Section 4 — Trading Flow (4.3)

```
Signal → Portfolio Target → Risk Preflight → Order Intent → Execution Router → Exchange Adapter → Fill → Position / PnL Reconciliation
```

Phase 3 implements: **Risk Preflight → Order Intent → Execution Router → Fill → Position / PnL Reconciliation** (paper, no exchange adapter).

### Section 7 — Security Rules

| Rule | Status |
|---|---|
| Default paper, no default live | ✅ Unbypassable guard at execution service boundary |
| Risk preflight required for orders | ✅ `risk_decision_id` required for order creation |
| Orders rejected without valid risk decision | ✅ `INVALID_RISK_DECISION` / `RISK_REJECTED` |
| State changes auditable, replayable, reconcileable | ✅ Events + audit for every state change, fill, reconciliation |
| Retry must be idempotent | ✅ `client_order_id` idempotency with `IDEMPOTENCY_CONFLICT` (409) |
| Decimal arithmetic for monetary values | ✅ Weighted-average price, PnL, fill quantities all `Decimal` |

### Section 9 — Development Phases

| Phase | Status |
|---|---|
| Phase 0: Architecture & baseline | ✅ |
| Phase 1: Control & data skeleton | ✅ |
| Phase 2: Research closed-loop | ✅ |
| **Phase 3: Paper trading closed-loop** | **✅ This delivery** |
| Phase 4: Exchange adapter & production | 🔲 |

### Section 11 — Acceptance Criteria

| Criterion | Status |
|---|---|
| Backend starts, health/core APIs available | ✅ |
| Order state machine, risk preflight, paper mode tests pass | ✅ (65 tests) |
| All models have idempotency, audit, error response | ✅ |
| No hardcoded keys, no default live, no bypass path | ✅ |
| Decimal, idempotency, risk decision binding, unified error format | ✅ |

---

## 3. Verification Summary

| Check | Result |
|---|---|
| `pytest` (65 tests) | 65 passed, 0 failed |
| `compileall` | All modules clean |
| `uvicorn` smoke test | `/health` 200, `/api/v1/system/status` 200 |

## 4. Phase 3 Uncompleted Items (Deferred to Phase 4)

- **Exchange adapter**: No real exchange REST/WebSocket connection
- **Live order routing**: Structurally blocked by paper-only guard
- **Kill switch**: No `POST /api/v1/system/kill-switch` endpoint
- **Approvals**: No strategy publishing or live-switch approval workflow
- **PostgreSQL/Redis**: In-memory storage only
- **Position PnL mark-to-market**: Positions only update on fill; no periodic mark-to-market against current ticker price
- **Order rejection during fill**: No exchange-level rejection simulation
- **Reconciliation auto-correction**: Only detects discrepancies; no auto-correction
- **Fill streaming**: No WebSocket for real-time fill notifications