"""Live-mode authorization: the single gate for every live trading path.

Three independent conditions must ALL hold before a live order is allowed:

1. **Deployment flag** — ``QUANT_LIVE_TRADING_ENABLED=true`` (ops-level,
   off by default; cannot be granted via API).
2. **Governance approval** — an APPROVED ``live_switch`` approval that has
   not expired (default TTL 24h). Create → approve via /governance APIs.
3. **Exchange credentials** — a usable live/testnet connection record for
   the target exchange (see CredentialService).

Every gate failure raises LIVE_TRADING_NOT_ALLOWED so existing callers
and tests keep their contract; ``diagnose()`` explains which gate failed.
"""

from typing import Any

from app.core.config import settings
from app.core.errors import QuantError
from app.core.logging import get_logger
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc
from app.models.enums import ApprovalResourceType, ApprovalStatus

logger = get_logger(__name__)


class LiveModeService:
    def __init__(self, store: Any):
        self._store = store

    # ── gate ─────────────────────────────────────────────────────────

    def assert_live_allowed(self, account_id: str = "paper-main", exchange: str | None = None) -> None:
        """Raise LIVE_TRADING_NOT_ALLOWED unless all three gates open."""
        diagnosis = self.diagnose(account_id, exchange)
        if diagnosis["authorized"]:
            return
        raise QuantError(
            "LIVE_TRADING_NOT_ALLOWED",
            f"Live trading blocked: {diagnosis['blocking_gates']}",
            status_code=403,
            details=diagnosis,
        )

    def is_live_authorized(self, account_id: str = "paper-main", exchange: str | None = None) -> bool:
        return self.diagnose(account_id, exchange)["authorized"]

    def diagnose(self, account_id: str = "paper-main", exchange: str | None = None) -> dict:
        gates = {
            "deployment_flag": settings.live_trading_enabled,
            "governance_approval": self._active_live_approval(account_id) is not None,
            "exchange_credentials": self._has_usable_credentials(exchange),
        }
        blocking = [name for name, ok in gates.items() if not ok]
        approval = self._active_live_approval(account_id)
        return {
            "account_id": account_id,
            "exchange": exchange,
            "authorized": not blocking,
            "gates": gates,
            "blocking_gates": blocking,
            "approval_id": approval.approval_id if approval else None,
            "approval_expires_at": approval.expires_at.isoformat() if approval else None,
            "checked_at": now_utc().isoformat(),
        }

    # ── approval path ────────────────────────────────────────────────

    def _active_live_approval(self, account_id: str) -> Any | None:
        """Newest non-expired APPROVED live_switch approval for account."""
        best = None
        for approval in self._store.approvals.values():
            if approval.resource_type != ApprovalResourceType.LIVE_SWITCH:
                continue
            if approval.resource_id != account_id:
                continue
            if approval.status != ApprovalStatus.APPROVED:
                continue
            if approval.is_expired():
                continue
            if best is None or (approval.decided_at or approval.created_at) > (best.decided_at or best.created_at):
                best = approval
        return best

    def request_authorization(self, account_id: str, requested_by: str, exchange: str | None = None, ttl_seconds: int = 86400) -> Any:
        """Create the governance approval that (once decided) opens gate 2."""
        return self._store.approval_service.create(
            resource_type=ApprovalResourceType.LIVE_SWITCH.value,
            resource_id=account_id,
            requested_by=requested_by,
            title=f"Switch account {account_id} to LIVE trading" + (f" on {exchange}" if exchange else ""),
            details=(
                "Approving this request authorizes live order execution for this account until the "
                "approval expires. Requires QUANT_LIVE_TRADING_ENABLED=true and configured exchange credentials."
            ),
            idempotency_key=None,
        )

    def revoke_authorization(self, account_id: str, operator: str) -> dict:
        """Expire every active live_switch approval for the account."""
        revoked = 0
        for approval in self._store.approvals.values():
            if (
                approval.resource_type == ApprovalResourceType.LIVE_SWITCH
                and approval.resource_id == account_id
                and approval.status == ApprovalStatus.APPROVED
                and not approval.is_expired()
            ):
                approval.status = ApprovalStatus.EXPIRED
                revoked += 1
        if revoked:
            event_bus.publish(DomainEvent(
                event_type=event_type("live_mode", "authorization_revoked"),
                event_id=new_event_id("live"),
                event_time=now_utc(),
                version=1,
                actor=operator,
                resource_type="account",
                resource_id=account_id,
                payload={"revoked_approvals": revoked},
            ))
        logger.warning("live_authorization_revoked", account_id=account_id, revoked=revoked, operator=operator)
        return {"account_id": account_id, "revoked_approvals": revoked}

    # ── credentials gate ─────────────────────────────────────────────

    def _has_usable_credentials(self, exchange: str | None) -> bool:
        records = [
            r for r in self._store.exchange_connections.values()
            if r.get("environment") in ("live", "testnet")
            and r.get("enabled")
            and (r.get("credential_token") or r.get("secret_ref"))
        ]
        if not records:
            return False
        if exchange is None:
            return True
        return any(r.get("adapter_name") == exchange.lower() for r in records)
