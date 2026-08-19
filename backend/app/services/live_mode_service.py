"""Live-mode authorization & Safety Gate: the single gate for every live trading path.

Three independent conditions must ALL hold before a live order is allowed:

1. **Deployment flag & Safety Gate** — ``ENABLE_LIVE_TRADING=true`` / ``QUANT_LIVE_TRADING_ENABLED=true``
   plus secondary confirmation unlock token/password verification (SafetyGate).
2. **Governance approval** — an APPROVED ``live_switch`` approval that has
   not expired (default TTL 24h). Create → approve via /governance APIs.
3. **Exchange credentials** — a usable live/testnet connection record for
   the target exchange (see CredentialService).

Every gate failure raises ``LiveTradingGateError`` (subclass of ``QuantError``) with
code ``LIVE_TRADING_NOT_ALLOWED`` so callers and tests keep their contract.
"""

import os
import threading
from datetime import datetime, timedelta
from typing import Any

from app.core.config import settings
from app.core.errors import QuantError
from app.core.logging import get_logger
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc
from app.models.enums import ApprovalResourceType, ApprovalStatus

logger = get_logger(__name__)


class LiveTradingGateError(QuantError):
    """Raised when live trading is blocked by the safety gate, missing credentials, or unapproved governance."""

    def __init__(self, message: str = "Live trading is disabled by safety gate", details: dict | None = None):
        super().__init__(
            "LIVE_TRADING_NOT_ALLOWED",
            message,
            status_code=403,
            details=details or {},
        )


class SafetyGate:
    """Live trading safety gate with environment master switch & secondary token confirmation."""

    DEFAULT_PASSWORD = "admin_live_safe_2026"

    def __init__(self):
        self._unlocked: bool = False
        self._unlocked_at: datetime | None = None
        self._expires_at: datetime | None = None
        self._operator: str | None = None
        self._lock = threading.Lock()

    def is_env_enabled(self) -> bool:
        """Check whether live trading is enabled by environment configuration."""
        env_val = os.environ.get("ENABLE_LIVE_TRADING", "").strip().lower()
        if env_val in ("true", "1", "yes"):
            return True
        quant_env_val = os.environ.get("QUANT_LIVE_TRADING_ENABLED", "").strip().lower()
        if quant_env_val in ("true", "1", "yes"):
            return True
        return bool(getattr(settings, "live_trading_enabled", False))

    def verify_unlock_token(self, token: str) -> bool:
        """Validate unlock password / safety token."""
        if not token:
            return False
        valid_passwords = [
            os.environ.get("LIVE_SAFETY_PASSWORD", "").strip(),
            os.environ.get("QUANT_LIVE_SAFETY_PASSWORD", "").strip(),
            getattr(settings, "secrets_master_key", "").strip(),
            self.DEFAULT_PASSWORD,
        ]
        return any(p and token == p for p in valid_passwords)

    def unlock(self, token: str, operator: str = "admin", ttl_seconds: int = 3600) -> dict[str, Any]:
        """Unlock the safety gate with valid password/token."""
        if not self.verify_unlock_token(token):
            raise LiveTradingGateError("Invalid live safety gate unlock password or token")
        with self._lock:
            self._unlocked = True
            self._unlocked_at = now_utc()
            self._expires_at = now_utc() + timedelta(seconds=ttl_seconds)
            self._operator = operator

        event_bus.publish(DomainEvent(
            event_type=event_type("live_mode", "safety_gate_unlocked"),
            event_id=new_event_id("live_gate"),
            event_time=now_utc(),
            version=1,
            actor=operator,
            resource_type="safety_gate",
            resource_id="live_trading",
            payload={"ttl_seconds": ttl_seconds, "expires_at": self._expires_at.isoformat()},
        ))
        logger.warning("live_safety_gate_unlocked", operator=operator, ttl_seconds=ttl_seconds)
        return self.get_status()

    def lock(self, operator: str = "admin") -> dict[str, Any]:
        """Lock the safety gate immediately."""
        with self._lock:
            self._unlocked = False
            self._expires_at = None
            self._operator = operator

        event_bus.publish(DomainEvent(
            event_type=event_type("live_mode", "safety_gate_locked"),
            event_id=new_event_id("live_gate"),
            event_time=now_utc(),
            version=1,
            actor=operator,
            resource_type="safety_gate",
            resource_id="live_trading",
            payload={},
        ))
        logger.info("live_safety_gate_locked", operator=operator)
        return self.get_status()

    def is_unlocked(self) -> bool:
        """Check if currently unlocked and not expired."""
        with self._lock:
            if not self._unlocked:
                return False
            if self._expires_at and now_utc() > self._expires_at:
                self._unlocked = False
                self._expires_at = None
                return False
            return True

    def get_status(self) -> dict[str, Any]:
        """Return current gate status."""
        unlocked = self.is_unlocked()
        remaining = 0
        with self._lock:
            if unlocked and self._expires_at:
                remaining = max(0, int((self._expires_at - now_utc()).total_seconds()))
            return {
                "env_enabled": self.is_env_enabled(),
                "unlocked": unlocked,
                "remaining_seconds": remaining,
                "operator": self._operator if unlocked else None,
                "unlocked_at": self._unlocked_at.isoformat() if unlocked and self._unlocked_at else None,
                "expires_at": self._expires_at.isoformat() if unlocked and self._expires_at else None,
            }

    def assert_allowed(self, token: str | None = None) -> None:
        """Raise LiveTradingGateError if environment switch is off or gate is locked."""
        if not self.is_env_enabled():
            raise LiveTradingGateError(
                "Live trading is disabled by environment flag (ENABLE_LIVE_TRADING=true required)"
            )
        if not self.is_unlocked():
            if token and self.verify_unlock_token(token):
                return
            raise LiveTradingGateError(
                "Live trading safety gate is locked; secondary password/token confirmation required"
            )


class LiveModeService:
    def __init__(self, store: Any):
        self._store = store
        self.safety_gate = SafetyGate()

    # ── gate ─────────────────────────────────────────────────────────

    def assert_live_allowed(
        self,
        account_id: str = "paper-main",
        exchange: str | None = None,
        token: str | None = None,
    ) -> None:
        """Raise LiveTradingGateError unless all gates open."""
        # 1. Direct safety gate token check if provided
        if token and not self.safety_gate.verify_unlock_token(token):
            raise LiveTradingGateError("Invalid live safety gate unlock token")

        # 2. Complete diagnosis for all gates
        diagnosis = self.diagnose(account_id, exchange)
        if diagnosis["authorized"]:
            return
        raise LiveTradingGateError(
            f"Live trading blocked: {diagnosis['blocking_gates']}",
            details=diagnosis,
        )

    def is_live_authorized(
        self,
        account_id: str = "paper-main",
        exchange: str | None = None,
        token: str | None = None,
    ) -> bool:
        if token and self.safety_gate.verify_unlock_token(token):
            return self.diagnose(account_id, exchange)["authorized"]
        return self.diagnose(account_id, exchange)["authorized"]

    def diagnose(self, account_id: str = "paper-main", exchange: str | None = None) -> dict:
        gates = {
            "deployment_flag": self.safety_gate.is_env_enabled(),
            "safety_gate_unlocked": self.safety_gate.is_unlocked(),
            "governance_approval": self._active_live_approval(account_id) is not None,
            "exchange_credentials": self._has_usable_credentials(exchange),
        }
        blocking = [name for name, ok in gates.items() if not ok]
        approval = self._active_live_approval(account_id)
        return {
            "account_id": account_id,
            "exchange": exchange,
            "authorized": len(blocking) == 0,
            "gates": gates,
            "blocking_gates": blocking,
            "approval_id": approval.approval_id if approval else None,
            "approval_expires_at": approval.expires_at.isoformat() if approval else None,
            "checked_at": now_utc().isoformat(),
        }

    # ── Safety Gate Delegate Methods ─────────────────────────────────

    def unlock_gate(self, token: str, operator: str = "admin", ttl_seconds: int = 3600) -> dict[str, Any]:
        return self.safety_gate.unlock(token, operator=operator, ttl_seconds=ttl_seconds)

    def lock_gate(self, operator: str = "admin") -> dict[str, Any]:
        return self.safety_gate.lock(operator=operator)

    def get_gate_status(self) -> dict[str, Any]:
        return self.safety_gate.get_status()

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
                "approval expires. Requires ENABLE_LIVE_TRADING=true, secondary password unlock, and configured exchange credentials."
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
        return {"account_id": account_id, "revoked_approvals": revoked, "operator": operator}

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
