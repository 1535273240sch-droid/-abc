# Phase 4: Approval Expiry Lifecycle — Conformance Review

> Generated: 2026-08-09
> Scope: `backend/` only
> Mode: **paper / simulation only** — no real network, no real keys, no live trading, no production deployment

---

## 1. Implemented

### Deterministic `expire_due()` — `app/services/approval_service.py`

```python
def expire_due(self, now: datetime | None = None) -> list[str]
```

- Accepts an injectable `now` for deterministic testing (defaults to `utcnow()`)
- Transitions every `pending` approval whose `expires_at` has passed to `expired`
- Returns the list of transitioned `approval_id`s
- **Idempotent**: second sweep returns `[]` (already-expired approvals skipped)
- Publishes `governance.approval_expired.v1` per expired approval

### Consuming paths refresh expiry state

| Path | Behavior |
|---|---|
| `get_approval()` | Calls `_refresh_expiry()` → lazy-expires if pending & past due, publishes event |
| `list_approvals()` | Calls `_refresh_expiry()` on each pending approval |
| `ApprovalService.decide()` | Checks `status == EXPIRED or is_expired()` FIRST → `APPROVAL_EXPIRED` (400) |
| `KillSwitchService.recover()` | Checks `status == EXPIRED or is_expired()` before pending → `APPROVAL_EXPIRED` (400), kill switch stays active |

### Versioned expiry event contract

`governance.approval_expired.v1` DomainEvent:
- `version = 1`
- `resource_type = "approval"`
- `resource_id = approval_id`
- `actor = "system"` (automated expiry, not a user action)
- `payload` includes `approval_id`, `resource_type`, `resource_id`, `status="expired"`, `expired_at`

### Modified Files

| File | Change |
|---|---|
| `app/services/approval_service.py` | Added `expire_due()`, `_refresh_expiry()`; enriched event payload; reordered `decide()` expiry check first |
| `app/services/kill_switch_service.py` | `recover()` checks `status==EXPIRED or is_expired()` before pending → `APPROVAL_EXPIRED` |
| `tests/test_api.py` | Added 7 expiry tests |

---

## 2. Test Evidence

**7 new expiry tests** (172 total, all passing):

| Test | Verifies |
|---|---|
| `test_approval_expire_due` | pending → expired via expire_due with injected now |
| `test_approval_expire_due_idempotent` | second sweep returns empty list |
| `test_approval_expire_then_decide_blocked` | decide on expired → `APPROVAL_EXPIRED` |
| `test_approval_expire_due_event_bus` | event version=1, resource_id, actor=system, payload fields |
| `test_approval_list_refreshes_expiry` | list() refreshes to expired |
| `test_approval_get_refreshes_expiry` | get() refreshes to expired |
| `test_approval_expired_kill_switch_recovery_blocked` | expired recovery → `APPROVAL_EXPIRED`, kill switch stays active |

---

## 3. Verification Summary

| Check | Result |
|---|---|
| `pytest` (172 tests) | 172 passed, 0 failed |
| `compileall` | All modules clean |
| `uvicorn` smoke test | `HEALTH` 200, `STATUS` 200 |
| | Approval created → `pending` |
| | `DECIDE` → 200 `approved` |
| | `DUP_DECIDE` → 400 `APPROVAL_ALREADY_DECIDED` |
| | `KS_RECOVER_MISSING` → 404 `NOT_FOUND` |
| | `LIVE` → 403 `LIVE_TRADING_NOT_ALLOWED` |
| | `ORDER_BLOCKED` → 503 `KILL_SWITCH_ACTIVE` |

---

## 4. Design Notes

- **Actor convention**: `expire_due` uses `actor="system"` because expiry is an automated lifecycle transition, not a user decision. This is consistent with the existing `system` actor used for `system.startup` and other automated events.
- **Expiry is lazy + explicit**: `expire_due()` provides an explicit sweep; `get/list/decide/recover` also refresh on read to guarantee a stale `pending` never slips through as decidable.
- **No side effects**: expiry only changes approval status; it does not touch orders, positions, kill switch, exchange, or keys.

---

## 5. Explicitly NOT Implemented / Remaining Limits

- **No distributed/production scheduler**: `expire_due()` is a manual/on-read sweep. There is no cron/background worker that periodically expires approvals. In a multi-replica deployment, a scheduler would be required.
- **No authentication / RBAC**: `actor`/`decided_by` are trusted strings.
- **No persistence**: in-memory only; expiry state is lost on restart.
- **No real exchange connection**: out of scope, paper-only.
- **`expires_at` precision**: truncated to whole seconds at creation (`replace(second=0, microsecond=0)`), inheriting existing Approval model behavior.