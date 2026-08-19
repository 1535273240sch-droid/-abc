"""Tests for Multi-Channel Webhook Notifications (Milestone M3).

Covers:
1. WeChat Work Markdown payload generation and color highlight rules.
2. Feishu Post rich-text payload generation.
3. DingTalk HMAC-SHA256 Base64 signing algorithm and Markdown payload.
4. Message truncation logic (>4096 characters).
5. 3-attempt exponential backoff retry mechanism (1s, 2s, 4s) and timeout control.
6. KillSwitchService.trigger() integration with critical alert broadcast.
7. Alert REST API endpoints (/status, /send, /config, /).
8. Edge cases: interface contract verification, event bus publication, store-less execution, error fault tolerance.
"""

import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.parse
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db.memory import InMemoryStore
from app.events.bus import DomainEvent, event_bus, event_type
from app.main import app
from app.models.enums import ApprovalResourceType, ApprovalStatus, KillSwitchStatus
from app.services.alert_notification_service import (
    AlertLevel,
    AlertNotificationService,
    DEFAULT_BACKOFF_FACTORS,
    MAX_MESSAGE_LENGTH,
    truncate_text,
)
from app.services.kill_switch_service import KillSwitchService


# ?? 1. WeChat Work Payload Tests ?????????????????????????????????????

def test_wechat_work_payload_formatting_and_colors():
    service = AlertNotificationService()

    # Critical severity -> warning color (red/orange)
    rec_crit = {
        "title": "??????",
        "message": "?????????",
        "severity": "critical",
        "source": "risk_guard",
        "created_at": "2026-08-18T02:00:00Z",
        "details": {"account_equity": 50000, "threshold": 60000},
    }
    payload_crit = service.build_wechat_work_payload(rec_crit)
    assert payload_crit["msgtype"] == "markdown"
    content_crit = payload_crit["markdown"]["content"]
    assert '<font color="warning">????????</font>' in content_crit
    assert '<font color="warning">CRITICAL</font>' in content_crit
    assert "**????**: `risk_guard`" in content_crit
    assert "?????????" in content_crit
    assert "account_equity" in content_crit

    # Info severity -> info color (green)
    rec_info = {
        "title": "??????",
        "message": "CTA-Trend-Follower ?????",
        "severity": "info",
        "source": "strategy_engine",
        "created_at": "2026-08-18T02:00:00Z",
        "details": {},
    }
    payload_info = service.build_wechat_work_payload(rec_info)
    content_info = payload_info["markdown"]["content"]
    assert '<font color="info">????????</font>' in content_info
    assert '<font color="info">INFO</font>' in content_info

    # Warning severity -> comment color
    rec_warn = {
        "title": "??????",
        "message": "?? 120ms",
        "severity": "warning",
        "source": "market_feed",
        "created_at": "2026-08-18T02:00:00Z",
        "details": None,
    }
    payload_warn = service.build_wechat_work_payload(rec_warn)
    content_warn = payload_warn["markdown"]["content"]
    assert '<font color="comment">????????</font>' in content_warn
    assert '<font color="comment">WARNING</font>' in content_warn


# ?? 2. Feishu Post Rich-Text Payload Tests ???????????????????????????

def test_feishu_payload_formatting():
    service = AlertNotificationService()
    record = {
        "title": "???????",
        "message": "Binance BTCUSDT ??????",
        "severity": "critical",
        "source": "market_depth",
        "created_at": "2026-08-18T02:30:00Z",
        "details": {"bid_ask_spread_pct": 0.05},
    }
    payload = service.build_feishu_payload(record)
    assert payload["msg_type"] == "post"
    post_zh = payload["content"]["post"]["zh_cn"]
    assert post_zh["title"] == "???????????????"
    elements = post_zh["content"][0]
    assert any("??: CRITICAL" in el.get("text", "") for el in elements)
    assert any("??: market_depth" in el.get("text", "") for el in elements)
    assert any("Binance BTCUSDT ??????" in el.get("text", "") for el in elements)
    assert any("bid_ask_spread_pct" in el.get("text", "") for el in elements)


# ?? 3. DingTalk Signature and Payload Tests ??????????????????????????

def test_dingtalk_signature_algorithm():
    secret = "SEC_test_secret_key_123456"
    ts = 1600000000000

    ts_str, sign = AlertNotificationService.calculate_dingtalk_sign(secret, ts)
    assert ts_str == "1600000000000"

    # Independently verify the signature calculation step-by-step
    string_to_sign = f"{ts}\n{secret}"
    expected_hmac = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    expected_base64 = base64.b64encode(expected_hmac).decode("utf-8")
    expected_sign = urllib.parse.quote_plus(expected_base64)

    assert sign == expected_sign
    assert len(sign) > 0


def test_dingtalk_payload_formatting():
    service = AlertNotificationService()
    record = {
        "title": "??????",
        "message": "???????????? 1.5 BTC",
        "severity": "error",
        "source": "reconciliation",
        "created_at": "2026-08-18T02:40:00Z",
        "details": {"symbol": "BTCUSDT", "diff": 1.5},
    }
    payload = service.build_dingtalk_payload(record)
    assert payload["msgtype"] == "markdown"
    assert payload["markdown"]["title"] == "??????"
    text = payload["markdown"]["text"]
    assert "### ??????" in text
    assert "- **??**: ERROR" in text
    assert "- **??**: reconciliation" in text
    assert "???????????? 1.5 BTC" in text
    assert "diff" in text
    assert payload["at"]["isAtAll"] is False


# ?? 4. Message Truncation Tests ??????????????????????????????????????

def test_message_truncation_exceeding_4096_chars():
    long_text = "A" * 5000
    truncated = truncate_text(long_text, max_length=MAX_MESSAGE_LENGTH)
    assert len(truncated) == MAX_MESSAGE_LENGTH
    assert truncated.endswith("...(truncated)")
    assert truncated.startswith("AAAAA")

    # When text is within limit, no truncation should occur
    short_text = "Normal alert message"
    assert truncate_text(short_text, max_length=MAX_MESSAGE_LENGTH) == short_text

    # Verify that payload builders also respect truncation limit
    service = AlertNotificationService()
    record = {
        "title": "Super long alert",
        "message": "X" * 6000,
        "severity": "warning",
        "source": "audit",
        "created_at": "2026-08-18T02:00:00Z",
        "details": {"huge": "Y" * 1000},
    }
    wechat_payload = service.build_wechat_work_payload(record)
    assert len(wechat_payload["markdown"]["content"]) <= MAX_MESSAGE_LENGTH

    dingtalk_payload = service.build_dingtalk_payload(record)
    assert len(dingtalk_payload["markdown"]["text"]) <= MAX_MESSAGE_LENGTH


# ?? 5. 3-Attempt Exponential Backoff & Timeout Tests ?????????????????

def test_http_retry_backoff_on_transient_failures_and_success():
    sleep_calls = []
    service = AlertNotificationService(sleep_func=lambda s: sleep_calls.append(s), timeout=5.0)

    # Attempt 1: 500 Internal Server Error
    # Attempt 2: 429 Too Many Requests
    # Attempt 3: 200 OK with {"errcode": 0}
    mock_resp_500 = urllib.error.HTTPError(
        url="http://test", code=500, msg="Server Error", hdrs={}, fp=BytesIO(b"error")
    )
    mock_resp_429 = urllib.error.HTTPError(
        url="http://test", code=429, msg="Rate Limited", hdrs={}, fp=BytesIO(b"rate limited")
    )

    mock_ok_resp = MagicMock()
    mock_ok_resp.status = 200
    mock_ok_resp.read.return_value = json.dumps({"errcode": 0, "errmsg": "ok"}).encode("utf-8")
    mock_ok_resp.__enter__.return_value = mock_ok_resp
    mock_ok_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", side_effect=[mock_resp_500, mock_resp_429, mock_ok_resp]):
        result = service._send_http_with_backoff(
            url="http://test-webhook",
            payload_data={"msgtype": "text"},
            channel_name="test_channel",
        )

    assert result == "sent"
    assert service.sent_count == 1
    assert service.failed_count == 0
    # Backoff waits: 1.0s after attempt 1, 2.0s after attempt 2
    assert sleep_calls == [1.0, 2.0]


def test_http_retry_exhaustion_on_persistent_failure():
    sleep_calls = []
    service = AlertNotificationService(sleep_func=lambda s: sleep_calls.append(s), timeout=5.0)

    # All 3 attempts fail with 503
    mock_resp_503 = urllib.error.HTTPError(
        url="http://test", code=503, msg="Service Unavailable", hdrs={}, fp=BytesIO(b"unavailable")
    )

    with patch("urllib.request.urlopen", side_effect=[mock_resp_503, mock_resp_503, mock_resp_503]):
        result = service._send_http_with_backoff(
            url="http://test-webhook",
            payload_data={"msgtype": "text"},
            channel_name="test_channel",
        )

    assert result == "http_503"
    assert service.sent_count == 0
    assert service.failed_count == 1
    # 2 sleeps between 3 attempts (1.0s, 2.0s)
    assert sleep_calls == [1.0, 2.0]


# ?? 6. KillSwitchService Integration with Critical Alert Broadcast ???

def test_kill_switch_trigger_broadcasts_critical_alert():
    store = InMemoryStore()
    kill_switch = store.kill_switch_service
    alert_service = store.alert_notification_service

    # Configure dummy webhook endpoints
    alert_service.configure_channel("wechat_work", {"key": "test_wechat_key"})
    alert_service.configure_channel("dingtalk", {"token": "test_dingtalk_token", "secret": "sec123"})

    mock_send = MagicMock(return_value={"wechat_work": True, "dingtalk": True})
    with patch.object(alert_service, "send_alert", side_effect=mock_send) as mock_method:
        state = kill_switch.trigger(
            triggered_by="risk_officer_alice",
            reason="Max equity drawdown 12.8% reached hard limit 10.0%",
        )

        assert state.status == KillSwitchStatus.ACTIVE
        assert state.triggered_by == "risk_officer_alice"
        assert "Max equity drawdown" in state.trigger_reason

        mock_method.assert_called_once()
        call_kwargs = mock_method.call_args.kwargs
        assert call_kwargs["level"] == AlertLevel.CRITICAL
        assert "??????" in call_kwargs["title"]
        assert "risk_officer_alice" in call_kwargs["message"]
        assert call_kwargs["metadata"]["triggered_by"] == "risk_officer_alice"
        assert call_kwargs["metadata"]["status"] == "active"
        assert call_kwargs["source"] == "kill_switch"


def test_kill_switch_recover_broadcasts_info_alert():
    store = InMemoryStore()
    kill_switch = store.kill_switch_service
    alert_service = store.alert_notification_service

    # Trigger first
    kill_switch.trigger("admin", "test trigger")
    assert kill_switch.is_active()

    # Create approved approval
    approval_id = "appr-ks-recover-01"
    approval = MagicMock()
    approval.resource_type = ApprovalResourceType.KILL_SWITCH_RECOVERY
    approval.status = ApprovalStatus.APPROVED
    approval.is_expired.return_value = False
    store.approvals[approval_id] = approval

    with patch.object(alert_service, "send_alert") as mock_method:
        recovered_state = kill_switch.recover(
            recovered_by="admin_bob",
            reason="Market recovered, safe to resume",
            approval_id=approval_id,
            mode="paper",
        )
        assert recovered_state.status == KillSwitchStatus.INACTIVE
        assert recovered_state.recovered_by == "admin_bob"

        mock_method.assert_called_once()
        call_kwargs = mock_method.call_args.kwargs
        assert call_kwargs["level"] == AlertLevel.INFO
        assert "??????" in call_kwargs["title"]
        assert "admin_bob" in call_kwargs["message"]
        assert call_kwargs["metadata"]["approval_id"] == approval_id


# ?? 7. Dynamic Channel Configuration and Status Tests ????????????????

def test_channel_configuration_and_status():
    service = AlertNotificationService()
    assert service.status()["wechat_work_enabled"] is False
    assert service.status()["feishu_enabled"] is False
    assert service.status()["dingtalk_enabled"] is False

    service.configure_channel("wechat_work", {"key": "bot_key_wechat_001"})
    assert service.status()["wechat_work_enabled"] is True
    assert "key=bot_key_wechat_001" in service._wechat_url

    service.configure_channel("feishu", {"token": "feishu_token_002", "secret": "feishu_sec"})
    assert service.status()["feishu_enabled"] is True
    assert "feishu_token_002" in service._feishu_url
    assert service._feishu_secret == "feishu_sec"

    service.configure_channel("dingtalk", {"token": "dt_token_003", "secret": "dt_sec_003"})
    assert service.status()["dingtalk_enabled"] is True
    assert "access_token=dt_token_003" in service._dingtalk_url
    assert service._dingtalk_secret == "dt_sec_003"


# ?? 8. REST API Integration Tests ????????????????????????????????????

def test_api_alert_endpoints():
    client = TestClient(app)

    # 1. GET /api/v1/alerts/status
    res_status = client.get("/api/v1/alerts/status")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert "wechat_work_enabled" in status_data
    assert "sent_count" in status_data

    # 2. POST /api/v1/alerts/config
    res_config = client.post(
        "/api/v1/alerts/config",
        json={"channel": "wechat_work", "config": {"key": "api_test_key"}},
    )
    assert res_config.status_code == 200
    assert res_config.json()["status"] == "success"
    assert res_config.json()["current_status"]["wechat_work_enabled"] is True

    # 3. POST /api/v1/alerts/send (or /api/v1/alerts/test)
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"errcode": 0}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        mock_url.return_value = mock_resp

        res_send = client.post(
            "/api/v1/alerts/send",
            json={
                "title": "API ????",
                "message": "???????????",
                "level": "warning",
                "channels": ["wechat_work"],
                "metadata": {"test_run": True},
            },
        )
        assert res_send.status_code == 200
        body = res_send.json()
        assert body["status"] == "success"
        assert "alert_id" in body
        assert body["channels"]["wechat_work"] == "sent"

    # 4. GET /api/v1/alerts (listing stored alerts)
    res_list = client.get("/api/v1/alerts")
    assert res_list.status_code == 200
    assert isinstance(res_list.json(), list)


# ?? 9. Contract & Edge Case Tests ????????????????????????????????????

def test_send_alert_interface_contract():
    store = InMemoryStore()
    service = AlertNotificationService(store=store)
    service.configure_channel("wechat_work", {"webhook_url": "http://mock-wechat"})
    service.configure_channel("feishu", {"webhook_url": "http://mock-feishu"})
    service.configure_channel("dingtalk", {"webhook_url": "http://mock-dingtalk"})

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"errcode": 0}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = service.send_alert(
            level=AlertLevel.CRITICAL,
            title="????",
            message="????????",
            channels=["wechat_work", "feishu", "dingtalk"],
            metadata={"key": "value"},
        )

    assert isinstance(res, dict)
    assert res.get("wechat_work") is True
    assert res.get("feishu") is True
    assert res.get("dingtalk") is True


def test_event_bus_domain_event_published():
    store = InMemoryStore()
    service = AlertNotificationService(store=store)

    with patch.object(event_bus, "publish") as mock_publish:
        service.alert(
            title="????????",
            message="?? DomainEvent ????",
            severity="warning",
            source="test_runner",
        )
        mock_publish.assert_called_once()
        event_arg = mock_publish.call_args[0][0]
        assert isinstance(event_arg, DomainEvent)
        assert event_arg.event_type == "alert.raised.v1"
        assert event_arg.resource_type == "alert"
        assert event_arg.payload["title"] == "????????"
        assert event_arg.payload["severity"] == "warning"


def test_kill_switch_without_alert_service_fault_tolerance():
    # If store has no alert service or it fails, kill switch state still transitions normally
    bare_store = MagicMock()
    bare_store.kill_switch_state = None
    bare_store.alert_notification_service = None
    bare_store.get_lock.return_value.__enter__ = MagicMock()
    bare_store.get_lock.return_value.__exit__ = MagicMock()

    service = KillSwitchService(bare_store)
    state = service.trigger("test_admin", "fault tolerance test")
    assert state.status == KillSwitchStatus.ACTIVE
