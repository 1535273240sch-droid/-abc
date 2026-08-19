"""Alert notification service: Multi-Channel Webhook (WeChat Work, Feishu, DingTalk) + Telegram + Email.

Critical for live trading ? surfaces rejections, reconciliation drift,
kill-switch triggers and process anomalies in real time.

Configuration via environment variables (all optional; disabled when unset):
    QUANT_ALERT_WECHAT_WORK_WEBHOOK ? WeChat Work webhook URL or bot key
    QUANT_ALERT_WECHAT_BOT_KEY      ? WeChat Work bot key
    QUANT_ALERT_FEISHU_WEBHOOK      ? Feishu bot webhook URL or bot token
    QUANT_ALERT_FEISHU_BOT_TOKEN    ? Feishu bot token
    QUANT_ALERT_FEISHU_SECRET       ? Feishu signature secret (optional)
    QUANT_ALERT_DINGTALK_WEBHOOK    ? DingTalk bot webhook URL or access token
    QUANT_ALERT_DINGTALK_TOKEN      ? DingTalk access token
    QUANT_ALERT_DINGTALK_SECRET     ? DingTalk signature secret (HMAC-SHA256)
    QUANT_ALERT_TELEGRAM_BOT_TOKEN  ? Telegram bot token
    QUANT_ALERT_TELEGRAM_CHAT_ID    ? Telegram chat/channel id
    QUANT_ALERT_EMAIL_SMTP_HOST     ? SMTP server host
    QUANT_ALERT_EMAIL_SMTP_PORT     ? SMTP port (default 465, SSL)
    QUANT_ALERT_EMAIL_FROM          ? sender address
    QUANT_ALERT_EMAIL_TO            ? recipient address (comma-separated ok)
    QUANT_ALERT_EMAIL_PASSWORD      ? SMTP password / app password

Every alert is also recorded into the store's alerts field and published
to the event bus, so the notification layer is purely additive.
"""

import base64
import hashlib
import hmac
import json
import os
import smtplib
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.mime.text import MIMEText
from enum import Enum
from typing import Any, Callable

from app.core.logging import get_logger
from app.events.bus import DomainEvent, event_bus, event_type, new_event_id, now_utc

logger = get_logger(__name__)


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


_SEVERITY_ORDER = {
    "info": 0,
    "warning": 1,
    "error": 2,
    "critical": 3,
}

MAX_MESSAGE_LENGTH = 4096
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_BACKOFF_FACTORS = (1.0, 2.0, 4.0)


def truncate_text(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    """Truncate text exceeding max_length and append ...(truncated)."""
    if len(text) <= max_length:
        return text
    suffix = "...(truncated)"
    cut_len = max(0, max_length - len(suffix))
    return text[:cut_len] + suffix


class AlertNotificationService:
    """Sends alerts to configured multi-channel webhooks; always records locally."""

    def __init__(
        self,
        store: Any = None,
        sleep_func: Callable[[float], None] = time.sleep,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self._store = store
        self._sleep_func = sleep_func
        self._timeout = timeout

        # Channel configurations from environment
        self._wechat_url = os.environ.get("QUANT_ALERT_WECHAT_WORK_WEBHOOK", "")
        self._wechat_key = os.environ.get("QUANT_ALERT_WECHAT_BOT_KEY", "")
        if self._wechat_key and not self._wechat_url:
            self._wechat_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={self._wechat_key}"

        self._feishu_url = os.environ.get("QUANT_ALERT_FEISHU_WEBHOOK", "")
        self._feishu_token = os.environ.get("QUANT_ALERT_FEISHU_BOT_TOKEN", "")
        self._feishu_secret = os.environ.get("QUANT_ALERT_FEISHU_SECRET", "")
        if self._feishu_token and not self._feishu_url:
            self._feishu_url = f"https://open.feishu.cn/open-apis/bot/v2/hook/{self._feishu_token}"

        self._dingtalk_url = os.environ.get("QUANT_ALERT_DINGTALK_WEBHOOK", "")
        self._dingtalk_token = os.environ.get("QUANT_ALERT_DINGTALK_TOKEN", "")
        self._dingtalk_secret = os.environ.get("QUANT_ALERT_DINGTALK_SECRET", "")
        if self._dingtalk_token and not self._dingtalk_url:
            self._dingtalk_url = f"https://oapi.dingtalk.com/robot/send?access_token={self._dingtalk_token}"

        self._tg_token = os.environ.get("QUANT_ALERT_TELEGRAM_BOT_TOKEN", "")
        self._tg_chat = os.environ.get("QUANT_ALERT_TELEGRAM_CHAT_ID", "")

        self._smtp_host = os.environ.get("QUANT_ALERT_EMAIL_SMTP_HOST", "")
        self._smtp_port = int(os.environ.get("QUANT_ALERT_EMAIL_SMTP_PORT", "465"))
        self._email_from = os.environ.get("QUANT_ALERT_EMAIL_FROM", "")
        self._email_to = os.environ.get("QUANT_ALERT_EMAIL_TO", "")
        self._email_password = os.environ.get("QUANT_ALERT_EMAIL_PASSWORD", "")

        self.sent_count = 0
        self.failed_count = 0

    # ?? Channel Configuration Methods ????????????????????????????????

    def configure_channel(self, channel: str, config: dict[str, Any]) -> None:
        """Dynamically configure or update a notification channel at runtime."""
        channel_name = channel.lower()
        if channel_name in ("wechat_work", "wechat", "wecom"):
            if "webhook_url" in config:
                self._wechat_url = config["webhook_url"]
            elif "key" in config or "bot_key" in config:
                key = config.get("key") or config.get("bot_key")
                self._wechat_key = key
                self._wechat_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
        elif channel_name == "feishu":
            if "webhook_url" in config:
                self._feishu_url = config["webhook_url"]
            elif "token" in config or "bot_token" in config:
                token = config.get("token") or config.get("bot_token")
                self._feishu_token = token
                self._feishu_url = f"https://open.feishu.cn/open-apis/bot/v2/hook/{token}"
            if "secret" in config:
                self._feishu_secret = config["secret"]
        elif channel_name == "dingtalk":
            if "webhook_url" in config:
                self._dingtalk_url = config["webhook_url"]
            elif "token" in config or "access_token" in config:
                token = config.get("token") or config.get("access_token")
                self._dingtalk_token = token
                self._dingtalk_url = f"https://oapi.dingtalk.com/robot/send?access_token={token}"
            if "secret" in config:
                self._dingtalk_secret = config["secret"]
        elif channel_name == "telegram":
            if "bot_token" in config:
                self._tg_token = config["bot_token"]
            if "chat_id" in config:
                self._tg_chat = config["chat_id"]
        elif channel_name == "email":
            if "smtp_host" in config:
                self._smtp_host = config["smtp_host"]
            if "smtp_port" in config:
                self._smtp_port = int(config["smtp_port"])
            if "email_from" in config:
                self._email_from = config["email_from"]
            if "email_to" in config:
                self._email_to = config["email_to"]
            if "email_password" in config:
                self._email_password = config["email_password"]

    # ?? Public API ????????????????????????????????????????????????????

    def send_alert(
        self,
        level: AlertLevel | str,
        title: str,
        message: str,
        channels: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        source: str = "system",
    ) -> dict[str, bool]:
        """Dispatch alert conforming to Project Interface Contract.

        Returns a dictionary of channel_name -> bool success indicator.
        """
        lvl_str = level.value if isinstance(level, AlertLevel) else str(level).lower()
        record = self.alert(
            title=title,
            message=message,
            severity=lvl_str,
            source=source,
            details=metadata,
            channels=channels,
        )
        channel_results = record.get("channels", {})
        return {ch: (status == "sent") for ch, status in channel_results.items()}

    def alert(
        self,
        title: str,
        message: str,
        severity: str = "warning",
        source: str = "system",
        details: dict[str, Any] | None = None,
        channels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Record + dispatch an alert through specified/configured channels."""
        sev_str = severity.lower() if severity.lower() in _SEVERITY_ORDER else "warning"
        truncated_msg = truncate_text(message, MAX_MESSAGE_LENGTH)
        now = datetime.now(timezone.utc)

        merged_details = dict(details or {})
        merged_details.setdefault("title", title)
        merged_details.setdefault("message", truncated_msg)

        record = {
            "alert_id": f"alert-{new_event_id('ntf')}",
            "title": title,
            "message": truncated_msg,
            "severity": sev_str,
            "source": source,
            "code": "ALERT_NOTIFICATION",
            "status": "active",
            "first_seen_at": now,
            "last_seen_at": now,
            "created_at": now.isoformat(),
            "details": merged_details,
            "channels": {},
        }

        # Local store persistence
        if self._store is not None:
            try:
                lock = getattr(self._store, "get_lock", None)
                if callable(lock):
                    with self._store.get_lock():
                        self._persist_alert(record)
                else:
                    self._persist_alert(record)
            except Exception as exc:  # noqa: BLE001
                logger.warning("alert_local_record_error", error=str(exc)[:200])

        # Determine target channels
        target_channels = self._resolve_channels(channels)

        # Dispatch across active channels
        for ch in target_channels:
            if ch in ("wechat_work", "wechat", "wecom"):
                record["channels"]["wechat_work"] = self._send_wechat_work(record)
            elif ch == "feishu":
                record["channels"]["feishu"] = self._send_feishu(record)
            elif ch == "dingtalk":
                record["channels"]["dingtalk"] = self._send_dingtalk(record)
            elif ch == "telegram":
                record["channels"]["telegram"] = self._send_telegram(self._format_text(record))
            elif ch == "email":
                record["channels"]["email"] = self._send_email(title, self._format_text(record))

        # Domain event publication
        try:
            event_bus.publish(
                DomainEvent(
                    event_type=event_type("alert", "raised"),
                    event_id=new_event_id("alert"),
                    event_time=now_utc(),
                    version=1,
                    actor=source,
                    resource_type="alert",
                    resource_id=record["alert_id"],
                    payload={"severity": sev_str, "title": title, "channels": list(record["channels"].keys())},
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("alert_event_publish_error", error=str(exc)[:200])

        logger.info("alert_raised", severity=sev_str, title=title, channels=record["channels"])
        return record

    def status(self) -> dict[str, Any]:
        """Return readiness and operational statistics across channels."""
        return {
            "wechat_work_enabled": bool(self._wechat_url),
            "feishu_enabled": bool(self._feishu_url),
            "dingtalk_enabled": bool(self._dingtalk_url),
            "telegram_enabled": bool(self._tg_token and self._tg_chat),
            "email_enabled": bool(self._smtp_host and self._email_from and self._email_to),
            "sent_count": self.sent_count,
            "failed_count": self.failed_count,
        }

    # ?? DingTalk Signature Computation ???????????????????????????????

    @staticmethod
    def calculate_dingtalk_sign(secret: str, timestamp: int | str | None = None) -> tuple[str, str]:
        """Compute DingTalk HMAC-SHA256 Base64 URL-encoded signature."""
        if timestamp is None:
            ts_str = str(round(time.time() * 1000))
        else:
            ts_str = str(timestamp)
        string_to_sign = f"{ts_str}\n{secret}"
        hmac_code = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign_base64 = base64.b64encode(hmac_code).decode("utf-8")
        sign = urllib.parse.quote_plus(sign_base64)
        return ts_str, sign

    # ?? Payload Builders ??????????????????????????????????????????????

    def build_wechat_work_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        """Construct WeChat Work Markdown message payload with color highlights."""
        sev = record["severity"]
        # WeChat Work markdown supports <font color="warning">, <font color="info">, <font color="comment">
        if sev in ("critical", "error"):
            color = "warning"
        elif sev == "info":
            color = "info"
        else:
            color = "comment"

        title = record["title"]
        source = record["source"]
        created_at = record["created_at"]
        message = record["message"]
        details = record.get("details")

        content_lines = [
            f"### <font color=\"{color}\">?{title}?</font>",
            f"> **????**: <font color=\"{color}\">{sev.upper()}</font>",
            f"> **????**: `{source}`",
            f"> **????**: `{created_at}`",
            f"> **????**: {message}",
        ]
        if details:
            details_str = json.dumps(details, ensure_ascii=False)
            content_lines.append(f"> **????**: `{truncate_text(details_str, 500)}`")

        content = truncate_text("\n".join(content_lines), MAX_MESSAGE_LENGTH)
        return {
            "msgtype": "markdown",
            "markdown": {
                "content": content,
            },
        }

    def build_feishu_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        """Construct Feishu Post rich text message payload."""
        sev = record["severity"].upper()
        title = f"????????{record['title']}"
        source = record["source"]
        created_at = record["created_at"]
        message = record["message"]
        details = record.get("details")

        elements = [
            {"tag": "text", "text": f"??: {sev}\n"},
            {"tag": "text", "text": f"??: {source}\n"},
            {"tag": "text", "text": f"??: {created_at}\n"},
            {"tag": "text", "text": f"??: {message}\n"},
        ]
        if details:
            details_str = json.dumps(details, ensure_ascii=False)
            elements.append({"tag": "text", "text": f"??: {truncate_text(details_str, 500)}\n"})

        payload = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": title,
                        "content": [elements],
                    }
                }
            },
        }
        return payload

    def build_dingtalk_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        """Construct DingTalk Markdown message payload."""
        sev = record["severity"].upper()
        title = record["title"]
        source = record["source"]
        created_at = record["created_at"]
        message = record["message"]
        details = record.get("details")

        text_lines = [
            f"### {title}",
            "",
            f"- **??**: {sev}",
            f"- **??**: {source}",
            f"- **??**: {created_at}",
            f"- **??**: {message}",
        ]
        if details:
            details_str = json.dumps(details, ensure_ascii=False)
            text_lines.append(f"- **??**: `{truncate_text(details_str, 500)}`")

        text = truncate_text("\n".join(text_lines), MAX_MESSAGE_LENGTH)
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text,
            },
            "at": {
                "isAtAll": False,
            },
        }

    # ?? Channel Sender Implementations with Exponential Backoff ??????

    def _send_http_with_backoff(
        self,
        url: str,
        payload_data: dict[str, Any],
        channel_name: str,
        backoff_factors: tuple[float, ...] = DEFAULT_BACKOFF_FACTORS,
    ) -> str:
        """Execute HTTP POST with 3-attempt exponential backoff retry and 5s timeout."""
        data_bytes = json.dumps(payload_data).encode("utf-8")
        headers = {"Content-Type": "application/json; charset=utf-8"}

        last_error = ""
        max_attempts = len(backoff_factors)

        for attempt in range(max_attempts):
            try:
                req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    resp_status = resp.status
                    resp_body = resp.read().decode("utf-8", errors="ignore")

                    if 200 <= resp_status < 300:
                        # Check webhook-level error codes if present in response json
                        try:
                            res_json = json.loads(resp_body)
                            # WeChat/DingTalk return errcode: 0, Feishu returns code: 0
                            errcode = res_json.get("errcode", res_json.get("code", 0))
                            if errcode != 0:
                                errmsg = res_json.get("errmsg", res_json.get("msg", f"code_{errcode}"))
                                logger.warning(
                                    f"{channel_name}_webhook_errcode",
                                    errcode=errcode,
                                    errmsg=errmsg,
                                    attempt=attempt + 1,
                                )
                                self.failed_count += 1
                                return f"errcode_{errcode}"
                        except Exception:
                            pass

                        self.sent_count += 1
                        return "sent"

                    last_error = f"http_{resp_status}"
            except urllib.error.HTTPError as exc:
                last_error = f"http_{exc.code}"
                if exc.code not in (429, 500, 502, 503, 504) and attempt == 0:
                    logger.warning(f"{channel_name}_http_client_error", code=exc.code, attempt=attempt + 1)
            except Exception as exc:  # noqa: BLE001
                last_error = f"error: {str(exc)[:80]}"
                logger.warning(f"{channel_name}_send_attempt_failed", attempt=attempt + 1, error=str(exc)[:200])

            # Backoff before next retry if not last attempt
            if attempt < max_attempts - 1:
                backoff_wait = backoff_factors[attempt]
                self._sleep_func(backoff_wait)

        self.failed_count += 1
        logger.error(f"{channel_name}_all_retries_exhausted", error=last_error)
        return last_error

    def _send_wechat_work(self, record: dict[str, Any]) -> str:
        if not self._wechat_url:
            return "disabled"
        payload = self.build_wechat_work_payload(record)
        return self._send_http_with_backoff(self._wechat_url, payload, "wechat_work")

    @staticmethod
    def _calculate_feishu_sign(timestamp: int, secret: str) -> str:
        string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
        h = hmac.new(secret.encode("utf-8"), string_to_sign, digestmod=hashlib.sha256).digest()
        return base64.b64encode(h).decode("utf-8")

    def _send_feishu(self, record: dict[str, Any]) -> str:
        if not self._feishu_url:
            return "disabled"
        payload = self.build_feishu_payload(record)
        if self._feishu_secret:
            ts = int(time.time())
            payload["timestamp"] = str(ts)
            payload["sign"] = self._calculate_feishu_sign(ts, self._feishu_secret)
        return self._send_http_with_backoff(self._feishu_url, payload, "feishu")

    def _send_dingtalk(self, record: dict[str, Any]) -> str:
        if not self._dingtalk_url:
            return "disabled"

        target_url = self._dingtalk_url
        if self._dingtalk_secret:
            ts, sign = self.calculate_dingtalk_sign(self._dingtalk_secret)
            separator = "&" if "?" in target_url else "?"
            target_url = f"{target_url}{separator}timestamp={ts}&sign={sign}"

        payload = self.build_dingtalk_payload(record)
        return self._send_http_with_backoff(target_url, payload, "dingtalk")

    def _send_telegram(self, text: str) -> str:
        if not (self._tg_token and self._tg_chat):
            return "disabled"
        try:
            url = f"https://api.telegram.org/bot{self._tg_token}/sendMessage"
            payload = urllib.parse.urlencode({
                "chat_id": self._tg_chat,
                "text": truncate_text(text, 4000),
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload, method="POST")
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
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
        if not (self._smtp_host and self._email_from and self._email_to):
            return "disabled"
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

    # ?? Helper Routines ???????????????????????????????????????????????

    def _resolve_channels(self, requested_channels: list[str] | None) -> list[str]:
        if requested_channels:
            return [c.lower() for c in requested_channels]
        # Auto-detect all enabled channels if none specified
        active: list[str] = []
        if self._wechat_url:
            active.append("wechat_work")
        if self._feishu_url:
            active.append("feishu")
        if self._dingtalk_url:
            active.append("dingtalk")
        if self._tg_token and self._tg_chat:
            active.append("telegram")
        if self._smtp_host and self._email_from and self._email_to:
            active.append("email")
        return active

    def _persist_alert(self, record: dict[str, Any]) -> None:
        alerts = getattr(self._store, "alerts", None)
        if isinstance(alerts, dict):
            alerts[record["alert_id"]] = record
        elif isinstance(alerts, list):
            alerts.append(record)

    def _format_text(self, record: dict[str, Any]) -> str:
        icon_map = {
            "info": "??",
            "warning": "??",
            "error": "?",
            "critical": "??",
        }
        icon = icon_map.get(record["severity"], "??")
        lines = [
            f"{icon} [{record['severity'].upper()}] {record['title']}",
            f"??: {record['source']}",
            f"??: {record['created_at']}",
            "",
            record["message"],
        ]
        if record.get("details"):
            lines.append("")
            lines.append("??: " + truncate_text(json.dumps(record["details"], ensure_ascii=False), 500))
        return "\n".join(lines)
