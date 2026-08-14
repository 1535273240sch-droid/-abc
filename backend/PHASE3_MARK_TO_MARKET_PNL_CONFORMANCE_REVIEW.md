# Phase 3: Mark-to-Market PnL — Conformance Review

> Generated: 2026-08-09
> Scope: `backend/` only
> Mode: **paper / simulation only** — no real network, no real keys, no live trading, no production deployment

---

## 1. Implemented

### Mark-to-Market API

| Endpoint | Method | Status | Description |
|---|---|---|---|
| `POST /api/v1/positions/mark-to-market` | POST | 200 | Refresh paper position PnL by mark price |
| `GET /api/v1/positions` | GET | 200 | List positions (reflects updated current_price/unrealized_pnl) |

### Computation

For each position matching `account_id` + `symbol`:
- **BUY**: `unrealized_pnl = (mark_price - entry_price) × quantity`
- **SELL**: `unrealized_pnl = (entry_price - mark_price) × quantity`
- `current_price = mark_price`
- All values use `Decimal` arithmetic; result quantized to 0.01

### Modified Files

| File | Change |
|---|---|
| `app/services/position_service.py` | Added `mark_to_market()` method + `_assert_paper_only()` + `_parse_decimal()` helpers |
| `app/position/position.py` | Added `GET /api/v1/positions` only (unchanged) |
| `app/api/v1/position.py` | Added `POST /api/v1/positions/mark-to-market` endpoint with audit |
| `app/schemas/position.py` | **New** — `MarkToMarketRequest`/`MarkToMarketResponse` |
| `app/models/enums.py` | Added `POSITION_MTM_UPDATED` audit event type |
| `app/db/memory.py` | Added `mtm_logs` storage for idempotency |
| `tests/test_api.py` | Added 9 MTM tests |

### Safety Boundaries

| Guard | Enforcement |
|---|---|
| No order creation | MTM only updates positions; `test_mark_to_market_no_order_side_effect` verifies orders unchanged |
| No risk preflight bypass | MTM does not create orders |
| No live trading | `_assert_paper_only()` → 403 `LIVE_TRADING_NOT_ALLOWED` |
| Idempotency | `idempotency_key` dedup via `mtm_logs` |
| Audit events | `position.mtm_updated` recorded |
| Versioned events | `position.mtm_updated.v1` published |
| `trace_id` | Propagated through audit events |

---

## 2. Test Evidence

**9 new tests** (149 total, all passing):

| Test | Verifies |
|---|---|
| `test_mark_to_market_buy_position` | 200, upnl=5000.00 for 0.5 BTC buy at 95000, mark 105000 |
| `test_mark_to_market_lower_price` | 200, upnl=-2500.00 for mark 90000 |
| `test_mark_to_market_live_blocked` | 403 LIVE_TRADING_NOT_ALLOWED |
| `test_mark_to_market_invalid_price` | 400 |
| `test_mark_to_market_idempotent` | Same idempotency_key → same result |
| `test_mark_to_market_audit_event` | `position.mtm_updated` in audit trail |
| `test_mark_to_market_event_bus` | `position.mtm_updated.v1` versioned event |
| `test_mark_to_market_trace_id` | trace_id propagated via X-Request-ID |
| `test_mark_to_market_no_order_side_effect` | Orders unchanged after MTM |

---

## 3. Verification Summary

| Check | Result |
|---|---|
| `pytest` (149 tests) | 149 passed, 0 failed |
| `compileall` | All modules clean |
| `uvicorn` smoke test | `/health` 200, `/api/v1/system/status` 200 |
| | `POST /api/v1/positions/mark-to-market` (paper) → **200** `upnl=5000.00` `price=105000.00` |
| | Same call with `idempotency_key` → same result (idempotent) |
| | `GET /api/v1/positions` → `current_price=105000.00` `unrealized_pnl=5000.00` (persisted) |
| | `POST /api/v1/positions/mark-to-market` (live) → **403** `LIVE_TRADING_NOT_ALLOWED` |
| | `GET /api/v1/orders` → count=0 (no side effects) |

---

## 4. Explicitly NOT Implemented (Real Production)

- No real exchange price feed — mark price is user-provided
- No order creation — pure position PnL update
- No risk preflight bypass — no order path
- No authentication / RBAC — no login, JWT, or permission enforcement
- No persistence — in-memory only
- No live trading — structurally blocked by paper-only guard
- No multi-symbol batch MTM — single symbol per call