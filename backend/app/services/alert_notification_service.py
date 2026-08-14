"""Alert notification service: Telegram + email channels.

Critical for live trading — surfaces rejections, reconciliation drift,
kill-switch triggers and process anomalies in real time.

Configuration via environment variables (all optional; disabled when unset):
    QUANT_ALERT_TELEGRAM_BOT_TOKEN   — Telegram bot token
    QUANT_ALERT_TELEGRAM_CHAT_ID     — Telegram chat/channel id
    QUANT_ALERT_EMAIL_SMTP_HOST      — SMTP server host
    QUANT_ALERT_EMAIL_SMTP_PORT      — SMTP port (default 465, SSL)
    QUANT_ALERT_EMAIL_FROM           — sender address
    QUANT_ALERT_EMAIL_TO             — recipient address (comma-separated ok)
    QUANT_ALERT_EMAIL_PASSWORD       — SMTP password / app password

Every alert is also recorded into the store's alerts field and published
to the event bus, so the notification layer is purely additive.
"""

import json
import smtplib
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc

logger = get_logger(__name__)

_SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


class AlertNotificationService:
    """Sends alerts to configured channels; always records locally."""

    def __init__(self, store: Any):
        self._store = store
        # env-driven config; read once at construction
        import os
        self._tg_token = os.environ.get("QUANT_ALERT_TELEGRAM_BOT_TOKEN", "")
        self._tg_chat = os.environ.get("QUANT_ALERT_TELEGRAM_CHAT_ID", "")
        self._smtp_host = os.environ.get("QUANT_ALERT_EMAIL_SMTP_HOST", "")
        self._smtp_port = int(os.environ.get("QUANT_ALERT_EMAIL_SMTP_PORT", "465"))
        self._email_from = os.environ.get("QUANT_ALERT_EMAIL_FROM", "")
        self._email_to = os.environ.get("QUANT_ALERT_EMAIL_TO", "")
        self._email_password = os.environ.get("QUANT_ALERT_EMAIL_PASSWORD", "")
        self.sent_count = 0
        self.failed_count = 0

    # ── public API ────────────────────────────────────────────────────

    def alert(
        self,
        title: str,
        message: str,
        severity: str = "warning",
        source: str = "system",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record + dispatch an alert through all configured channels."""
        severity = severity if severity in _SEVERITY_ORDER else "warning"
        record = {
            "alert_id": f"alert-{new_event_id('ntf')}",
            "title": title,
            "message": message,
            "severity": severity,
            "source": source,
            "details": details or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "channels": {},
        }

        # local record
        try:
            with self._store.get_lock():
                alerts = getattr(self._store, "alerts", None)
                if isinstance(alerts, dict):
                    alerts[record["alert_id"]] = record
                elif isinstance(alerts, list):
                    alerts.append(record)
        except Exception as exc:  # noqa: BLE001
            logger.warning("alert_local_record_error", error=str(exc)[:200])

        # dispatch
        text = self._format_text(record)
        if self._tg_token and self._tg_chat:
            record["channels"]["telegram"] = self._send_telegram(text)
        if self._smtp_host and self._email_from and self._email_to:
            record["channels"]["email"] = self._send_email(title, text)

        # domain event
        event_bus.publish(DomainEvent(
            event_type=event_type("alert", "raised"),
            event_id=new_event_id("alert"),
            event_time=now_utc(),
            version=1,
            actor=source,
            resource_type="alert",
            resource_id=record["alert_id"],
            payload={"severity": severity, "title": title},
        ))
        logger.info("alert_raised", severity=severity, title=title, channels=record["channels"])
        return record

    def status(self) -> dict[str, Any]:
        return {
            "telegram_enabled": bool(self._tg_token and self._tg_chat),
            "email_enabled": bool(self._smtp_host and self._email_from and self._email_to),
            "sent_count": self.sent_count,
            "failed_count": self.failed_count,
        }

    # ── channel senders ───────────────────────────────────────────────

    def _format_text(self, record: dict[str, Any]) -> str:
        icon = {"info": "ℹ️", "warning": "⚠️", "critical": "🔴"}[record["severity"]]
        lines = [
            f"{icon} [{record['severity'].upper()}] {record['title']}",
            f"来源: {record['source']}",
            f"时间: {record['created_at']}",
            "",
            record["message"],
        ]
        if record["details"]:
            lines.append("")
            lines.append("详情: " + json.dumps(record["details"], ensure_ascii=False)[:500])
        return "\n".join(lines)

    def _send_telegram(self, text: str) -> str:
        try:
            url = f"https://api.telegram.org/bot{self._tg_token}/sendMessage"
            payload = urllib.parse.urlencode({
                "chat_id": self._tg_chat,
                "text": text[:4000],
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    self.sent_count += 1
                    return "sent"
            self.failed_count += 1
            return f"http_{resp.status}"
        except Exception as exc:  # noqa: BLE001
            self.failed_count += 1
            logger.warning("telegram_send_error", error=str(exc)[:200])
            return f"error: {str(exc)[:80]}"

    def _send_email(self, subject: str, body: str) -> str:
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = f"[Quant] {subject}"
            msg["From"] = self._email_from
            msg["To"] = self._email_to
            recipients = [r.strip() for r in self._email_to.split(",") if r.strip()]
            with smtplib.SMTP_SSL(self._smtp_host, self._smtp_port, timeout=15) as server:
                if self._email_password:
                    server.login(self._email_from, self._email_password)
                server.sendmail(self._email_from, recipients, msg.as_string())
            self.sent_count += 1
            return "sent"
        except Exception as exc:  # noqa: BLE001
            self.failed_count += 1
            logger.warning("email_send_error", error=str(exc)[:200])
            return f"error: {str(exc)[:80]}"
