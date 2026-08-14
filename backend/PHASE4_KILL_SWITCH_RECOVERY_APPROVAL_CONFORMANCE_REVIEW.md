# Phase 4: Kill-Switch Recovery Approval Gate — Conformance Review

> Generated: 2026-08-09
> Scope: `backend/` only
> Mode: **paper / simulation only** — no real network, no real keys, no live trading, no production deployment

---

## 1. Implemented

### Approval Gate for Kill-Switch Recovery

**Before**: `KillSwitchService.recover()` accepted any caller with `recovered_by` + `reason` — no approval required.

**After**: `recover()` requires a valid `approval_id` that must be:
- Present → 404 `NOT_FOUND` if missing
- Resource type `kill_switch_recovery` → 400 `INVALID_APPROVAL_TYPE` if wrong
- Status `approved` → 400 `APPROVAL_PENDING` if pending, `APPROVAL_REJECTED` if rejected, `APPROVAL_EXPIRED` if expired
- Mode `paper` → 403 `LIVE_TRADING_NOT_ALLOWED` if live
- Kill switch must be active → 400 `INVALID_STATE` if already inactive

### Modified Files

| File | Change |
|---|---|
| `app/models/enums.py` | Added `KILL_SWITCH_RECOVERY` to `ApprovalResourceType` |
| `app/schemas/governance.py` | Added `mode: str = "paper"` to `KillSwitchRecoverRequest`, `approval_id: str` |
| `app/services/kill_switch_service.py` | `recover()` now accepts `approval_id` + `mode`; validates approval existence, type, status, expiry, paper-only; added `_assert_paper_only()` |
| `app/api/v1/governance.py` | Passes `mode=body.mode` to service |
| `tests/test_api.py` | Added 6 new tests: missing/pending/rejected/wrong-type/duplicate/live-blocked |

---

## 2. Test Evidence

**18 kill-switch tests** (165 total, all passing):

| Test | Verifies |
|---|---|
| `test_kill_switch_default_state` | Default inactive |
| `test_kill_switch_trigger` | Trigger → active |
| `test_kill_switch_recover` | Approved recovery → inactive |
| `test_kill_switch_recover_without_trigger` | 400 INVALID_STATE |
| `test_kill_switch_blocks_order_intent` | 503 KILL_SWITCH_ACTIVE |
| `test_kill_switch_blocks_execution_fill` | 503 |
| `test_kill_switch_blocks_cancel` | 503 |
| `test_kill_switch_recover_audit_event` | Audit trail |
| `test_kill_switch_trigger_audit_event` | Audit trail |
| `test_kill_switch_event_bus` | Versioned event |
| `test_ks_recover_missing_approval` | 404 NOT_FOUND |
| `test_ks_recover_pending_approval` | 400 APPROVAL_PENDING |
| `test_ks_recover_rejected_approval` | 400 APPROVAL_REJECTED |
| `test_ks_recover_wrong_type_approval` | 400 INVALID_APPROVAL_TYPE |
| `test_ks_recover_duplicate_approval` | 400 INVALID_STATE (second call) |
| `test_ks_recover_live_blocked` | 403 LIVE_TRADING_NOT_ALLOWED |

---

## 3. Verification Summary

| Check | Result |
|---|---|
| `pytest` (165 tests) | 165 passed, 0 failed |
| `compileall` | All modules clean |
| `uvicorn` smoke test | `HEALTH` 200, `STATUS` 200 |
| | `APPROVED_RECOVER` → **200** `ks=inactive` |
| | `DUP_RECOVER` → **400** `INVALID_STATE` |
| | `MISSING` → **404** `NOT_FOUND` |
| | `PENDING` → **400** `APPROVAL_PENDING` |
| | `REJECTED` → **400** `APPROVAL_REJECTED` |
| | `WRONG_TYPE` → **400** `INVALID_APPROVAL_TYPE` |
| | `LIVE` → **403** `LIVE_TRADING_NOT_ALLOWED` |
| | `ORDER_BLOCKED` → **503** `KILL_SWITCH_ACTIVE` |
| | `ADAPTER_BLOCKED` → **503** `KILL_SWITCH_ACTIVE` |

---

## 4. Gap Closed vs. Previous Review

`PRODUCTION_GUARDRAILS_CONFORMANCE_REVIEW.md` §4 noted:
> "Kill switch recovery is audited but not approval-checked"

**This delivery closes that gap.** Recovery now requires a pre-approved `kill_switch_recovery` approval; all bypass paths are blocked with explicit error codes.

---

## 5. Explicitly NOT Implemented (Real Production)

- No real exchange connection
- No authentication / RBAC (actor/decided_by are trusted strings)
- No persistence (in-memory only)
- No live trading (structurally blocked)
- No expiry sweeper (approval expiry checked on use, not proactively)
- No multi-replica kill-switch state sharing