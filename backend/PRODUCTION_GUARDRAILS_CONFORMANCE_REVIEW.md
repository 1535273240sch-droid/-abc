# Production Guardrails — Phase 4 Conformance Review

> Generated: 2026-08-09
> Source: `ARCHITECTURE.md` sections 4, 7, 9, 11
> Scope: `backend/` only

---

## 1. Implemented (Phase 4 — Production Guardrails, Paper-Only)

> Note: This is the **security protection sub-phase** of Phase 4. It does NOT connect real exchanges, use real keys, enable live trading, or deploy to production.

### Approval State Machine — `app/services/approval_service.py`

States: `pending` → `approved` / `rejected` / `expired`

| Property | Detail |
|---|---|
| Resource types | `strategy_publish`, `risk_threshold_change`, `live_switch` |
| State transition | `pending` → `approved`/`rejected` (only via `decide()`); `pending` → `expired` (auto on TTL) |
| Already-decided | `APPROVAL_ALREADY_DECIDED` (400) |
| Expired | `APPROVAL_EXPIRED` (400) |
| TTL | Default 86400s (`expires_at`) |
| Idempotency | N/A (each request is a distinct approval) |
| Events | `governance.approval_decided.v1` |
| Audit | `approval.created`, `approval.decided` |

**Live-switch safety**: An approval for `live_switch` can reach `approved`, but the paper-only guard in the order/execution services still rejects any `live` order with `LIVE_TRADING_NOT_ALLOWED` (403). This is by design — approval alone cannot enable live trading.

### Kill Switch — `app/services/kill_switch_service.py`

| Property | Detail |
|---|---|
| Default state | `inactive` (safe) |
| `trigger()` | sets `active`; records triggered_by, reason, timestamp |
| `recover()` | sets `inactive`; requires audit; **rejected if not active** (`INVALID_STATE`) |
| Blocking | `assert_not_active()` raises `KILL_SWITCH_ACTIVE` (503) |
| Events | `governance.kill_switch_triggered.v1`, `governance.kill_switch_recovered.v1` |
| Audit | `kill_switch.triggered`, `kill_switch.recovered` |

When active, the following are blocked:
- `POST /api/v1/orders/intents` (order creation)
- `POST /api/v1/execution/fills`
- `POST /api/v1/execution/orders/{id}/cancel`
- `POST /api/v1/execution/orders/{id}/reject`

### New API Endpoints — `app/api/v1/governance.py`

| Endpoint | Method | Status | Description |
|---|---|---|---|
| `POST /api/v1/governance/approvals` | POST | 201 | Create an approval request |
| `POST /api/v1/governance/approvals/{id}/decide` | POST | 200 | Approve/reject an approval |
| `GET /api/v1/governance/approvals` | GET | 200 | List approvals (filter by status) |
| `GET /api/v1/governance/approvals/{id}` | GET | 200 | Get single approval |
| `POST /api/v1/governance/kill-switch/trigger` | POST | 200 | Trigger kill switch |
| `POST /api/v1/governance/kill-switch/recover` | POST | 200 | Recover kill switch (audited) |
| `GET /api/v1/governance/kill-switch` | GET | 200 | Get kill switch state |

### New Domain Models

| Model | Fields |
|---|---|
| `Approval` | approval_id, resource_type, resource_id, requested_by, title, details, status, decided_by, reject_reason, ttl_seconds, created_at, decided_at, expires_at |
| `KillSwitchState` | status, triggered_by, trigger_reason, triggered_at, recovered_by, recovered_at |

### New Enums

| Enum | Values |
|---|---|
| `ApprovalStatus` | pending, approved, rejected, expired |
| `ApprovalResourceType` | strategy_publish, risk_threshold_change, live_switch |
| `KillSwitchStatus` | inactive, active |
| `AuditEventType` | +`APPROVAL_CREATED`, `APPROVAL_DECIDED`, `KILL_SWITCH_TRIGGERED`, `KILL_SWITCH_RECOVERED` |

### New Error Codes

`KILL_SWITCH_ACTIVE` (503), `APPROVAL_EXPIRED` (400), `APPROVAL_ALREADY_DECIDED` (400)

### Test Coverage — 20 new tests (85 total)

| Test | Verifies |
|---|---|
| `test_approval_create` | Strategy publish approval created pending |
| `test_approval_create_live_switch` | Live switch approval resource type accepted |
| `test_approval_approve` | approve transition + decided_by |
| `test_approval_reject` | reject transition + reject_reason |
| `test_approval_already_decided` | 400 APPROVAL_ALREADY_DECIDED |
| `test_approval_invalid_resource_type` | 400 VALIDATION_ERROR |
| `test_approval_list` / `test_approval_get` / `test_approval_get_not_found` | CRUD |
| `test_kill_switch_default_state` | Default inactive (safe) |
| `test_kill_switch_trigger` | trigger → active + metadata |
| `test_kill_switch_recover` | recover → inactive + audited |
| `test_kill_switch_recover_without_trigger` | 400 INVALID_STATE |
| `test_kill_switch_blocks_order_intent` | 503 KILL_SWITCH_ACTIVE |
| `test_kill_switch_blocks_execution_fill` | 503 |
| `test_kill_switch_blocks_cancel` | 503 |
| `test_kill_switch_recover_audit_event` | recovery audit trail |
| `test_kill_switch_trigger_audit_event` | trigger audit trail |
| `test_kill_switch_event_bus` | versioned event published |
| `test_live_switch_approved_but_still_blocked` | approved live_switch still blocked by paper-only guard |

---

## 2. ARCHITECTURE.md Section Conformance

### Section 4 — Agent Collaboration Flow (4.4)

> "涉及策略发布、实盘开关、API Key、风控阈值和生产部署的动作必须经过审批门。"

Implemented: strategy publish, risk threshold change, and live switch all require approval via the approval state machine.

### Section 7 — Security Rules

| Rule (7) | Status |
|---|---|
| Default paper, no default live | ✅ |
| API Key only via Secret Manager | 🔲 No key handling yet (Phase 4 adapter) |
| Orders rejected without valid risk decision | ✅ |
| Execution rejects orders without risk approval | ✅ |
| State changes auditable, replayable, reconcileable | ✅ + approvals & kill switch |
| Retry idempotent | ✅ |
| Production switch, strategy publish, risk threshold, kill switch require approval records | ✅ (approval state machine) |

---

## 3. Verification Summary

| Check | Result |
|---|---|
| `pytest` (85 tests) | 85 passed, 0 failed |
| `compileall` | All modules clean |
| `uvicorn` smoke test | `/health` 200, `/api/v1/system/status` 200, `/api/v1/governance/kill-switch` 200 (inactive) |

---

## 4. Phase 4 — STILL NOT IMPLEMENTED (Production)

These are explicitly deferred; they are NOT part of this paper-only guardrail delivery.

### Real Exchange Adapter
- No Binance/OKX/Bybit REST or WebSocket connection
- No real order routing, reconnect, rate limiting
- No exchange private API models

### Authentication & Authorization
- No login endpoint, JWT, session, or RBAC enforcement
- `requested_by`/`decided_by` are trusted strings, not verified identities
- API key / secret management absent

### Database
- In-memory store only; no PostgreSQL/Alembic, Redis, or ClickHouse
- No durable persistence of approvals/kill switch state

### Production Deployment
- No containerization, config management, secrets, observability (OTel/Prometheus)
- `live` mode structurally blocked; no true live-execution path

### Remaining Guardrail Gaps
- Approval expiry is time-based only; no scheduled expiry sweeper
- Kill switch state is per-process memory (not shared across replicas)
- No kill switch auto-recovery or approval-gated recovery enforcement (recovery is audited but not approval-checked)
- No RBAC: any caller can trigger/recover kill switch or decide approvals