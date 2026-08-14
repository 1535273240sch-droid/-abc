import hashlib
from datetime import datetime, timezone
from typing import Any

from app.events.bus import now_utc


class AlertService:
    def __init__(self, store: Any):
        self._store = store

    def sync_market_quality(self, quality: dict) -> list[dict]:
        issues = quality.get("issues", [])
        active_ids: set[str] = set()
        for issue in issues:
            code = str(issue.get("code", "MARKET_DATA"))
            key = hashlib.sha1(f"market:{code}".encode()).hexdigest()[:12]
            alert_id = f"alert-market-{key}"
            active_ids.add(alert_id)
            alert = self._store.alerts.get(alert_id) or {
                "alert_id": alert_id,
                "severity": "critical" if code == "INVALID_PRICES" else "warning",
                "source": "market_data",
                "code": code,
                "status": "active",
                "first_seen_at": now_utc(),
                "last_seen_at": now_utc(),
                "details": issue,
            }
            alert["status"] = "active"
            alert["last_seen_at"] = now_utc()
            alert["details"] = issue
            self._store.alerts[alert_id] = alert

        for alert_id, alert in self._store.alerts.items():
            if alert.get("source") == "market_data" and alert_id not in active_ids:
                alert["status"] = "resolved"
                alert["last_seen_at"] = now_utc()
        return self.list_alerts()

    def list_alerts(self, status: str | None = None) -> list[dict]:
        alerts = list(self._store.alerts.values())
        if status:
            alerts = [alert for alert in alerts if alert.get("status") == status]
        default_time = datetime.min.replace(tzinfo=timezone.utc)
        return sorted(alerts, key=lambda alert: alert.get("last_seen_at", default_time), reverse=True)
