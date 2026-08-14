def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


def test_ready(client):
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
    assert resp.json()["checks"]["storage"] is True


def test_system_status(client):
    resp = client.get("/api/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["mode"] == "paper"
    assert data["app_version"]


def test_market_symbols(client):
    resp = client.get("/api/v1/market/symbols")
    assert resp.status_code == 200
    symbols = resp.json()
    assert len(symbols) >= 1
    assert symbols[0]["symbol"] == "BTCUSDT"
    assert symbols[0]["market_type"] == "spot"


def test_market_tickers(client):
    resp = client.get("/api/v1/market/tickers")
    assert resp.status_code == 200
    tickers = resp.json()
    assert len(tickers) >= 1
    assert "last_price" in tickers[0]


def test_strategies(client):
    resp = client.get("/api/v1/strategies")
    assert resp.status_code == 200
    strategies = resp.json()
    assert len(strategies) >= 1
    assert strategies[0]["strategy_id"] == "trend-btc"


def test_positions(client):
    resp = client.get("/api/v1/positions")
    assert resp.status_code == 200
    positions = resp.json()
    assert len(positions) >= 1
    assert positions[0]["symbol"] == "BTCUSDT"


def test_risk_preflight_approved(client):
    resp = client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": "paper-main",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.01000000",
            "price": "99900.00",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "approved"
    assert data["decision_id"]
    assert data["remaining_risk_budget"]


def test_risk_preflight_rejected(client):
    resp = client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": "paper-main",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "100.00000000",
            "price": "99900.00",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "rejected"
    assert data["reject_reason"]


def test_risk_preflight_live_mode_rejected(client):
    resp = client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": "paper-main",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.01000000",
            "price": "99900.00",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "live",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["decision"] == "rejected"


def test_risk_preflight_invalid_decimal_quantity(client):
    cases = [
        ("abc", "VALIDATION_ERROR"),
        ("", "VALIDATION_ERROR"),
        ("NaN", "VALIDATION_ERROR"),
        ("Infinity", "VALIDATION_ERROR"),
        ("-1.0", "VALIDATION_ERROR"),
    ]
    for qty, expected_code in cases:
        body = {
            "account_id": "paper-main",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": qty,
            "price": "99900.00",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "paper",
        }
        resp = client.post("/api/v1/risk/preflight", json=body)
        data = resp.json()
        if "error" in data:
            code = data["error"]["code"]
            details = data["error"].get("details", {})
        else:
            code = "ANOMALY"
            details = {}
        # Pydantic rejects empty string or non-numeric with VALIDATION_ERROR
        # Our service rejects NaN/Infinity/negative with VALIDATION_ERROR
        assert code == expected_code or code == "VALIDATION_ERROR", f"qty={qty!r} got {code}"


def test_risk_preflight_invalid_decimal_price(client):
    body = {
        "account_id": "paper-main",
        "symbol": "BTCUSDT",
        "side": "buy",
        "quantity": "0.01",
        "price": "NaN",
        "strategy_id": "trend-btc",
        "strategy_version": "1.0.0",
        "mode": "paper",
    }
    resp = client.post("/api/v1/risk/preflight", json=body)
    assert resp.status_code == 400
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] in ("VALIDATION_ERROR",)


def test_order_intent_success(client, approved_decision):
    resp = client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": "intent-001",
            "account_id": "paper-main",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "99900.00",
            "mode": "paper",
            "risk_decision_id": approved_decision["decision_id"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "new"
    assert data["client_order_id"] == "intent-001"
    assert data["risk_decision_id"] == approved_decision["decision_id"]


def test_order_intent_idempotent_same(client, approved_decision):
    payload = {
        "client_order_id": "intent-002",
        "account_id": "paper-main",
        "strategy_id": "trend-btc",
        "strategy_version": "1.0.0",
        "symbol": "BTCUSDT",
        "market_type": "spot",
        "side": "buy",
        "order_type": "limit",
        "quantity": "0.01000000",
        "limit_price": "99900.00",
        "mode": "paper",
        "risk_decision_id": approved_decision["decision_id"],
    }
    first = client.post("/api/v1/orders/intents", json=payload)
    second = client.post("/api/v1/orders/intents", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["client_order_id"] == second.json()["client_order_id"]
    assert first.json()["status"] == second.json()["status"]


def test_order_intent_idempotent_conflict(client, approved_decision):
    payload = {
        "client_order_id": "intent-conflict",
        "account_id": "paper-main",
        "strategy_id": "trend-btc",
        "strategy_version": "1.0.0",
        "symbol": "BTCUSDT",
        "market_type": "spot",
        "side": "buy",
        "order_type": "limit",
        "quantity": "0.01000000",
        "limit_price": "99900.00",
        "mode": "paper",
        "risk_decision_id": approved_decision["decision_id"],
    }
    client.post("/api/v1/orders/intents", json=payload)

    payload2 = payload.copy()
    payload2["quantity"] = "0.02000000"
    resp = client.post("/api/v1/orders/intents", json=payload2)
    assert resp.status_code == 409
    data = resp.json()
    assert data["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert "quantity" in data["error"]["details"]["conflicts"]


def test_order_intent_missing_risk_decision(client):
    resp = client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": "intent-003",
            "account_id": "paper-main",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "99900.00",
            "mode": "paper",
            "risk_decision_id": "nonexistent-decision",
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "INVALID_RISK_DECISION"


def test_order_intent_rejected_risk_decision(client):
    rejected = client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": "paper-main",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "100.00000000",
            "price": "99900.00",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
    ).json()
    assert rejected["decision"] == "rejected"

    resp = client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": "intent-004",
            "account_id": "paper-main",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "100.00000000",
            "limit_price": "99900.00",
            "mode": "paper",
            "risk_decision_id": rejected["decision_id"],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "RISK_REJECTED"


def test_order_intent_risk_decision_account_mismatch(client, approved_decision):
    resp = client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": "intent-mismatch-account",
            "account_id": "other-account",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "99900.00",
            "mode": "paper",
            "risk_decision_id": approved_decision["decision_id"],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "RISK_DECISION_MISMATCH"


def test_order_intent_risk_decision_symbol_mismatch(client, approved_decision):
    resp = client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": "intent-mismatch-symbol",
            "account_id": "paper-main",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "ETHUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "99900.00",
            "mode": "paper",
            "risk_decision_id": approved_decision["decision_id"],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "RISK_DECISION_MISMATCH"


def test_order_intent_risk_decision_side_mismatch(client, approved_decision):
    resp = client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": "intent-mismatch-side",
            "account_id": "paper-main",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "sell",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "99900.00",
            "mode": "paper",
            "risk_decision_id": approved_decision["decision_id"],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "RISK_DECISION_MISMATCH"


def test_order_intent_risk_decision_mode_mismatch(client, approved_decision):
    resp = client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": "intent-mismatch-mode",
            "account_id": "paper-main",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "99900.00",
            "mode": "live",
            "risk_decision_id": approved_decision["decision_id"],
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "LIVE_TRADING_NOT_ALLOWED"


def test_order_intent_live_mode_blocked(client):
    resp = client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": "intent-live-blocked",
            "account_id": "paper-main",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "99900.00",
            "mode": "live",
            "risk_decision_id": "any-decision",
        },
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["error"]["code"] == "LIVE_TRADING_NOT_ALLOWED"
    assert data["error"]["trace_id"]


def test_order_intent_invalid_mode_blocked(client):
    resp = client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": "intent-bad-mode",
            "account_id": "paper-main",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "99900.00",
            "mode": "production",
            "risk_decision_id": "any-decision",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_order_intent_risk_decision_strategy_id_mismatch(client, approved_decision):
    resp = client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": "intent-mismatch-strategy-id",
            "account_id": "paper-main",
            "strategy_id": "arb-eth",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "99900.00",
            "mode": "paper",
            "risk_decision_id": approved_decision["decision_id"],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "RISK_DECISION_MISMATCH"


def test_order_intent_risk_decision_strategy_version_mismatch(client, approved_decision):
    resp = client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": "intent-mismatch-strategy-ver",
            "account_id": "paper-main",
            "strategy_id": "trend-btc",
            "strategy_version": "2.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "99900.00",
            "mode": "paper",
            "risk_decision_id": approved_decision["decision_id"],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "RISK_DECISION_MISMATCH"


def test_order_intent_idempotent_conflict_limit_price(client, approved_decision):
    payload = {
        "client_order_id": "intent-conflict-price",
        "account_id": "paper-main",
        "strategy_id": "trend-btc",
        "strategy_version": "1.0.0",
        "symbol": "BTCUSDT",
        "market_type": "spot",
        "side": "buy",
        "order_type": "limit",
        "quantity": "0.01000000",
        "limit_price": "99900.00",
        "mode": "paper",
        "risk_decision_id": approved_decision["decision_id"],
    }
    client.post("/api/v1/orders/intents", json=payload)

    payload2 = payload.copy()
    payload2["limit_price"] = "88800.00"
    resp = client.post("/api/v1/orders/intents", json=payload2)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert "limit_price" in resp.json()["error"]["details"]["conflicts"]


def test_order_intent_idempotent_conflict_risk_decision_id(client, approved_decision):
    decision2 = client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": "paper-main",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.01000000",
            "price": "99900.00",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
    ).json()

    payload = {
        "client_order_id": "intent-conflict-risk-id",
        "account_id": "paper-main",
        "strategy_id": "trend-btc",
        "strategy_version": "1.0.0",
        "symbol": "BTCUSDT",
        "market_type": "spot",
        "side": "buy",
        "order_type": "limit",
        "quantity": "0.01000000",
        "limit_price": "99900.00",
        "mode": "paper",
        "risk_decision_id": approved_decision["decision_id"],
    }
    client.post("/api/v1/orders/intents", json=payload)

    payload2 = payload.copy()
    payload2["risk_decision_id"] = decision2["decision_id"]
    resp = client.post("/api/v1/orders/intents", json=payload2)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert "risk_decision_id" in resp.json()["error"]["details"]["conflicts"]


def test_error_response_includes_trace_id(client):
    resp = client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": "intent-trace-test",
            "account_id": "paper-main",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "99900.00",
            "mode": "paper",
            "risk_decision_id": "missing",
        },
        headers={"X-Request-ID": "test-trace-123"},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["trace_id"] == "test-trace-123"


def test_audit_event_includes_trace_id(client, approved_decision):
    resp = client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": "intent-trace-audit",
            "account_id": "paper-main",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "99900.00",
            "mode": "paper",
            "risk_decision_id": approved_decision["decision_id"],
        },
        headers={"X-Request-ID": "audit-trace-456"},
    )
    assert resp.status_code == 200

    audit_resp = client.get("/api/v1/audit/events")
    events = audit_resp.json()
    matching = [e for e in events if e["resource_id"] == "intent-trace-audit"]
    assert len(matching) >= 1
    assert matching[0]["trace_id"] == "audit-trace-456"


def test_event_bus_receives_risk_preflight_event(client):
    from app.events.bus import event_bus

    received = []

    def handler(event):
        received.append(event)

    event_bus.subscribe("risk.preflight.v1", handler)

    client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": "paper-main",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.01000000",
            "price": "99900.00",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
    )
    assert len(received) >= 1
    assert received[0].event_type == "risk.preflight.v1"
    assert received[0].payload["decision"] == "approved"


def test_event_bus_receives_order_intent_event(client, approved_decision):
    from app.events.bus import event_bus

    received = []

    def handler(event):
        received.append(event)

    event_bus.subscribe("order.intent_created.v1", handler)

    client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": "intent-evt-001",
            "account_id": "paper-main",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "99900.00",
            "mode": "paper",
            "risk_decision_id": approved_decision["decision_id"],
        },
    )
    assert len(received) >= 1
    assert received[0].event_type == "order.intent_created.v1"
    assert received[0].payload["symbol"] == "BTCUSDT"


def test_event_bus_counts(client, approved_decision):
    from app.events.bus import event_bus

    before = event_bus.counts().get("risk.preflight.v1", 0)
    client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": "paper-main",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.01000000",
            "price": "99900.00",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
    )
    after = event_bus.counts().get("risk.preflight.v1", 0)
    assert after == before + 1


def test_list_orders(client, approved_decision):
    client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": "intent-list-001",
            "account_id": "paper-main",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "99900.00",
            "mode": "paper",
            "risk_decision_id": approved_decision["decision_id"],
        },
    )
    resp = client.get("/api/v1/orders")
    assert resp.status_code == 200
    orders = resp.json()
    assert len(orders) == 1
    assert orders[0]["client_order_id"] == "intent-list-001"


def test_audit_events(client):
    client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": "paper-main",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.01000000",
            "price": "99900.00",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
    )
    resp = client.get("/api/v1/audit/events")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) >= 1
    assert any(e["event_type"] == "risk.preflight" for e in events)


def test_unified_error_format(client):
    resp = client.post(
        "/api/v1/orders/intents",
        json={
            "client_order_id": "intent-err-001",
            "account_id": "paper-main",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "limit",
            "quantity": "0.01000000",
            "limit_price": "99900.00",
            "mode": "paper",
            "risk_decision_id": "missing",
        },
    )
    assert resp.status_code == 400
    assert "error" in resp.json()
    assert "code" in resp.json()["error"]
    assert "message" in resp.json()["error"]


def test_cors_headers(client):
    resp = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_headers_rejected_origin(client):
    resp = client.options(
        "/health",
        headers={
            "Origin": "http://evil.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # If origin not in allowed list, CORS middleware should not return ACAO header
    assert "access-control-allow-origin" not in resp.headers or resp.headers["access-control-allow-origin"] != "http://evil.com"


def test_control_exchange_paper_connection_test(client):
    resp = client.post("/api/v1/control/exchanges/paper-paper/test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "paper_ready"
    assert data["runtime_ready"] is True


def test_control_exchange_disabled_connection_test(client):
    resp = client.post("/api/v1/control/exchanges/binance-paper/test")
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"


# ── Backtest / Research Tests ────────────────────────────────────────────────

def test_backtest_success(client):
    resp = client.post(
        "/api/v1/research/backtests",
        json={
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "data_snapshot": "snap_parquet_20260801",
            "fee_model": "maker_0.02pct_taker_0.04pct",
            "slippage_model": "conservative_1.5bps",
            "initial_capital": "100000.00",
            "mode": "paper",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "completed"
    assert data["strategy_id"] == "trend-btc"
    assert data["strategy_version"] == "1.0.0"
    assert data["net_profit"] is not None
    assert data["sharpe_ratio"] is not None
    assert data["max_drawdown"] is not None
    assert data["win_rate"] is not None
    assert data["total_trades"] > 0
    assert data["data_snapshot"] == "snap_parquet_20260801"
    assert data["run_environment"] == "paper-backtest-engine-v1"
    assert data["initial_capital"] == "100000.00"
    assert data["mode"] == "paper"
    assert data["idempotency_key"] is None


def test_backtest_returns_metrics(client):
    resp = client.post(
        "/api/v1/research/backtests",
        json={
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "initial_capital": "50000.00",
            "mode": "paper",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["net_profit"].startswith("-") or data["net_profit"].startswith("0") or data["net_profit"][0].isdigit()
    assert data["sharpe_ratio"].replace(".", "").replace("-", "").isdigit()
    assert "%" in data["max_drawdown"]
    assert "%" in data["win_rate"]
    assert 50 <= data["total_trades"] <= 600


def test_backtest_invalid_strategy(client):
    resp = client.post(
        "/api/v1/research/backtests",
        json={
            "strategy_id": "nonexistent",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_backtest_wrong_version(client):
    resp = client.post(
        "/api/v1/research/backtests",
        json={
            "strategy_id": "trend-btc",
            "strategy_version": "9.9.9",
            "mode": "paper",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_STRATEGY_VERSION"


def test_backtest_live_mode_blocked(client):
    resp = client.post(
        "/api/v1/research/backtests",
        json={
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "live",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "LIVE_TRADING_NOT_ALLOWED"


def test_backtest_invalid_capital(client):
    resp = client.post(
        "/api/v1/research/backtests",
        json={
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "initial_capital": "abc",
            "mode": "paper",
        },
    )
    assert resp.status_code == 400


def test_backtest_idempotent(client):
    payload = {
        "strategy_id": "arb-eth",
        "strategy_version": "1.0.0",
        "idempotency_key": "bt-dup-key-001",
        "mode": "paper",
    }
    first = client.post("/api/v1/research/backtests", json=payload)
    second = client.post("/api/v1/research/backtests", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["backtest_id"] == second.json()["backtest_id"]
    assert first.json()["idempotency_key"] == "bt-dup-key-001"


def test_backtest_get_by_id(client):
    create = client.post(
        "/api/v1/research/backtests",
        json={
            "strategy_id": "grid-bnb",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
    )
    assert create.status_code == 201
    bt_id = create.json()["backtest_id"]

    resp = client.get(f"/api/v1/research/backtests/{bt_id}")
    assert resp.status_code == 200
    assert resp.json()["backtest_id"] == bt_id
    assert resp.json()["strategy_id"] == "grid-bnb"


def test_backtest_get_not_found(client):
    resp = client.get("/api/v1/research/backtests/nonexistent-bt")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_backtest_list(client):
    client.post("/api/v1/research/backtests", json={
        "strategy_id": "trend-btc", "strategy_version": "1.0.0", "mode": "paper",
    })
    client.post("/api/v1/research/backtests", json={
        "strategy_id": "arb-eth", "strategy_version": "1.0.0", "mode": "paper",
    })
    resp = client.get("/api/v1/research/backtests")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


def test_backtest_audit_event(client):
    client.post("/api/v1/research/backtests", json={
        "strategy_id": "trend-btc", "strategy_version": "1.0.0", "mode": "paper",
    })
    resp = client.get("/api/v1/audit/events")
    assert resp.status_code == 200
    events = resp.json()
    assert any(e["event_type"] == "backtest.completed" for e in events)


def test_backtest_event_bus(client):
    from app.events.bus import event_bus
    received = []
    def handler(event):
        received.append(event)
    event_bus.subscribe("research.backtest_completed.v1", handler)
    client.post("/api/v1/research/backtests", json={
        "strategy_id": "trend-btc", "strategy_version": "1.0.0", "mode": "paper",
    })
    assert len(received) >= 1
    assert received[0].event_type == "research.backtest_completed.v1"
    assert received[0].payload["strategy_id"] == "trend-btc"


def test_backtest_traceability(client, approved_decision):
    resp = client.post(
        "/api/v1/research/backtests",
        json={
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
        headers={"X-Request-ID": "bt-trace-test"},
    )
    assert resp.status_code == 201
    bt_id = resp.json()["backtest_id"]

    get_resp = client.get(f"/api/v1/research/backtests/{bt_id}")
    assert get_resp.status_code == 200
    bt = get_resp.json()
    assert bt["created_at"] is not None
    assert bt["completed_at"] is not None
    assert bt["strategy_id"] == "trend-btc"
    assert bt["strategy_version"] == "1.0.0"

    audit_resp = client.get("/api/v1/audit/events")
    matching = [e for e in audit_resp.json() if e["resource_id"] == bt_id]
    assert len(matching) >= 1
    assert matching[0]["trace_id"] == "bt-trace-test"


# ── Execution / Paper Lifecycle Tests ────────────────────────────────────────

def _create_and_preflight(client):
    decision = client.post("/api/v1/risk/preflight", json={
        "account_id": "paper-main", "symbol": "BTCUSDT", "side": "buy",
        "quantity": "0.01000000", "price": "99900.00",
        "strategy_id": "trend-btc", "strategy_version": "1.0.0", "mode": "paper",
    }).json()
    assert decision["decision"] == "approved"
    return decision


def _create_order(client, decision_id, cid="exec-test-001"):
    return client.post("/api/v1/orders/intents", json={
        "client_order_id": cid, "account_id": "paper-main",
        "strategy_id": "trend-btc", "strategy_version": "1.0.0",
        "symbol": "BTCUSDT", "market_type": "spot", "side": "buy",
        "order_type": "limit", "quantity": "0.01000000", "limit_price": "99900.00",
        "mode": "paper", "risk_decision_id": decision_id,
    }).json()


def test_execution_fill_partial(client):
    d = _create_and_preflight(client)
    _create_order(client, d["decision_id"], "exec-partial")
    resp = client.post("/api/v1/execution/fills", json={
        "client_order_id": "exec-partial", "fill_quantity": "0.00400000", "fill_price": "99900.00",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "partially_filled"
    assert data["filled_quantity"] == "0.00400000"
    assert data["fill_id"]


def test_execution_fill_full(client):
    d = _create_and_preflight(client)
    _create_order(client, d["decision_id"], "exec-full")
    resp = client.post("/api/v1/execution/fills", json={
        "client_order_id": "exec-full", "fill_quantity": "0.01000000", "fill_price": "99900.00",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "filled"
    assert data["filled_quantity"] == "0.01000000"


def test_execution_fill_exceeds_remaining(client):
    d = _create_and_preflight(client)
    _create_order(client, d["decision_id"], "exec-exceed")
    resp = client.post("/api/v1/execution/fills", json={
        "client_order_id": "exec-exceed", "fill_quantity": "0.02000000", "fill_price": "99900.00",
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_FILL"


def test_execution_fill_order_not_found(client):
    resp = client.post("/api/v1/execution/fills", json={
        "client_order_id": "nonexistent", "fill_quantity": "0.00100000", "fill_price": "99900.00",
    })
    assert resp.status_code == 404


def test_execution_cancel_success(client):
    d = _create_and_preflight(client)
    _create_order(client, d["decision_id"], "exec-cancel")
    resp = client.post("/api/v1/execution/orders/exec-cancel/cancel", json={"client_order_id": "exec-cancel"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_execution_cancel_already_filled(client):
    d = _create_and_preflight(client)
    _create_order(client, d["decision_id"], "exec-cancel-filled")
    client.post("/api/v1/execution/fills", json={
        "client_order_id": "exec-cancel-filled", "fill_quantity": "0.01000000", "fill_price": "99900.00",
    })
    resp = client.post("/api/v1/execution/orders/exec-cancel-filled/cancel", json={"client_order_id": "exec-cancel-filled"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_execution_reject_success(client):
    d = _create_and_preflight(client)
    _create_order(client, d["decision_id"], "exec-reject")
    resp = client.post("/api/v1/execution/orders/exec-reject/reject", json={"client_order_id": "exec-reject"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_execution_reject_already_filled(client):
    d = _create_and_preflight(client)
    _create_order(client, d["decision_id"], "exec-reject-filled")
    client.post("/api/v1/execution/fills", json={
        "client_order_id": "exec-reject-filled", "fill_quantity": "0.01000000", "fill_price": "99900.00",
    })
    resp = client.post("/api/v1/execution/orders/exec-reject-filled/reject", json={"client_order_id": "exec-reject-filled"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_execution_state_transitions_partial_then_full(client):
    d = _create_and_preflight(client)
    _create_order(client, d["decision_id"], "exec-ptf")
    r1 = client.post("/api/v1/execution/fills", json={
        "client_order_id": "exec-ptf", "fill_quantity": "0.00400000", "fill_price": "99900.00",
    })
    assert r1.json()["status"] == "partially_filled"
    r2 = client.post("/api/v1/execution/fills", json={
        "client_order_id": "exec-ptf", "fill_quantity": "0.00600000", "fill_price": "100000.00",
    })
    assert r2.json()["status"] == "filled"
    assert r2.json()["filled_quantity"] == "0.01000000"


def test_execution_position_update_on_fill(client):
    d = _create_and_preflight(client)
    _create_order(client, d["decision_id"], "exec-pos")
    resp = client.post("/api/v1/execution/fills", json={
        "client_order_id": "exec-pos", "fill_quantity": "0.01000000", "fill_price": "99900.00",
    })
    assert resp.status_code == 200
    pos_updates = resp.json()["position_updates"]
    assert pos_updates is not None
    assert pos_updates["created"] is True or pos_updates["quantity"] is not None


def test_execution_reconciliation_run(client):
    d = _create_and_preflight(client)
    _create_order(client, d["decision_id"], "exec-rec")
    client.post("/api/v1/execution/fills", json={
        "client_order_id": "exec-rec", "fill_quantity": "0.01000000", "fill_price": "99900.00",
    })
    resp = client.post("/api/v1/execution/reconciliation?account_id=paper-main")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("consistent", "discrepancy")
    assert data["reconciliation_id"]


def test_execution_reconciliation_logs(client):
    resp = client.get("/api/v1/execution/reconciliation")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_execution_fill_audit_event(client, approved_decision):
    _create_order(client, approved_decision["decision_id"], "exec-audit-fill")
    client.post("/api/v1/execution/fills", json={
        "client_order_id": "exec-audit-fill", "fill_quantity": "0.01000000", "fill_price": "99900.00",
    })
    resp = client.get("/api/v1/audit/events")
    assert any(e["event_type"] == "order.filled" for e in resp.json())


def test_execution_event_bus(client, approved_decision):
    from app.events.bus import event_bus
    received = []
    def handler(event):
        received.append(event)
    event_bus.subscribe("order.filled.v1", handler)
    _create_order(client, approved_decision["decision_id"], "exec-evt-bus")
    client.post("/api/v1/execution/fills", json={
        "client_order_id": "exec-evt-bus", "fill_quantity": "0.01000000", "fill_price": "99900.00",
    })
    assert len(received) >= 1
    assert received[0].event_type == "order.filled.v1"


def test_execution_trace_id_in_audit(client, approved_decision):
    _create_order(client, approved_decision["decision_id"], "exec-trace")
    client.post(
        "/api/v1/execution/fills",
        json={"client_order_id": "exec-trace", "fill_quantity": "0.01000000", "fill_price": "99900.00"},
        headers={"X-Request-ID": "exec-trace-abc"},
    )
    resp = client.get("/api/v1/audit/events")
    matching = [e for e in resp.json() if e["resource_id"] == "exec-trace"]
    assert len(matching) >= 1
    assert matching[0]["trace_id"] == "exec-trace-abc"


# ── Governance / Approval / Kill Switch Tests ────────────────────────────────

def test_approval_create(client):
    resp = client.post(
        "/api/v1/governance/approvals",
        json={
            "resource_type": "strategy_publish",
            "resource_id": "trend-btc@1.5.0",
            "requested_by": "researcher-a",
            "title": "Publish trend-btc v1.5.0",
            "details": "Sharpe 1.95, max drawdown -6.2%",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["resource_type"] == "strategy_publish"
    assert data["approval_id"]


def test_approval_create_live_switch(client):
    resp = client.post(
        "/api/v1/governance/approvals",
        json={
            "resource_type": "live_switch",
            "resource_id": "paper-main",
            "requested_by": "admin",
            "title": "Switch paper-main to live",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"


def test_approval_approve(client):
    appr = client.post("/api/v1/governance/approvals", json={
        "resource_type": "risk_threshold_change", "resource_id": "max_notional",
        "requested_by": "risk-officer", "title": "Raise max notional limit",
    }).json()
    resp = client.post(f"/api/v1/governance/approvals/{appr['approval_id']}/decide", json={
        "decision": "approved", "decided_by": "admin",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    assert resp.json()["decided_by"] == "admin"


def test_approval_reject(client):
    appr = client.post("/api/v1/governance/approvals", json={
        "resource_type": "strategy_publish", "resource_id": "arb-eth@2.0",
        "requested_by": "researcher-b", "title": "Publish arb-eth v2",
    }).json()
    resp = client.post(f"/api/v1/governance/approvals/{appr['approval_id']}/decide", json={
        "decision": "rejected", "decided_by": "admin", "reject_reason": "Sharpe too low",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert resp.json()["reject_reason"] == "Sharpe too low"


def test_approval_already_decided(client):
    appr = client.post("/api/v1/governance/approvals", json={
        "resource_type": "strategy_publish", "resource_id": "grid-bnb@2.0",
        "requested_by": "researcher-c", "title": "Publish grid-bnb v2",
    }).json()
    client.post(f"/api/v1/governance/approvals/{appr['approval_id']}/decide", json={
        "decision": "approved", "decided_by": "admin",
    })
    resp = client.post(f"/api/v1/governance/approvals/{appr['approval_id']}/decide", json={
        "decision": "rejected", "decided_by": "admin",
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "APPROVAL_ALREADY_DECIDED"


def test_approval_invalid_resource_type(client):
    resp = client.post("/api/v1/governance/approvals", json={
        "resource_type": "invalid_type", "resource_id": "x",
        "requested_by": "user", "title": "Test",
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_approval_list(client):
    resp = client.get("/api/v1/governance/approvals")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_approval_get(client):
    appr = client.post("/api/v1/governance/approvals", json={
        "resource_type": "strategy_publish", "resource_id": "test-id",
        "requested_by": "user", "title": "Get test",
    }).json()
    resp = client.get(f"/api/v1/governance/approvals/{appr['approval_id']}")
    assert resp.status_code == 200
    assert resp.json()["approval_id"] == appr["approval_id"]


def test_approval_get_not_found(client):
    resp = client.get("/api/v1/governance/approvals/nonexistent")
    assert resp.status_code == 404


def test_kill_switch_default_state(client):
    resp = client.get("/api/v1/governance/kill-switch")
    assert resp.status_code == 200
    assert resp.json()["status"] == "inactive"


def test_kill_switch_trigger(client):
    resp = client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Emergency maintenance",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
    assert resp.json()["triggered_by"] == "admin"
    assert resp.json()["trigger_reason"] == "Emergency maintenance"


def _create_ks_recovery_approval(client) -> str:
    appr = client.post("/api/v1/governance/approvals", json={
        "resource_type": "kill_switch_recovery", "resource_id": "system",
        "requested_by": "admin", "title": "Kill switch recovery approval",
    }).json()
    client.post(f"/api/v1/governance/approvals/{appr['approval_id']}/decide", json={
        "decision": "approved", "decided_by": "admin",
    })
    return appr["approval_id"]


def test_kill_switch_recover(client):
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Test trigger",
    })
    aid = _create_ks_recovery_approval(client)
    resp = client.post("/api/v1/governance/kill-switch/recover", json={
        "recovered_by": "operator", "reason": "Issue resolved",
        "approval_id": aid,
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "inactive"
    assert resp.json()["recovered_by"] == "operator"


def test_kill_switch_recover_without_trigger(client):
    aid = _create_ks_recovery_approval(client)
    resp = client.post("/api/v1/governance/kill-switch/recover", json={
        "recovered_by": "operator", "reason": "N/A", "approval_id": aid,
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_STATE"


def test_kill_switch_blocks_order_intent(client, approved_decision):
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Test block",
    })
    resp = client.post("/api/v1/orders/intents", json={
        "client_order_id": "ks-block-intent", "account_id": "paper-main",
        "strategy_id": "trend-btc", "strategy_version": "1.0.0",
        "symbol": "BTCUSDT", "market_type": "spot", "side": "buy",
        "order_type": "limit", "quantity": "0.01000000", "limit_price": "99900.00",
        "mode": "paper", "risk_decision_id": approved_decision["decision_id"],
    })
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "KILL_SWITCH_ACTIVE"


def test_kill_switch_blocks_execution_fill(client, approved_decision):
    _create_order(client, approved_decision["decision_id"], "ks-block-fill")
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Test block fill",
    })
    resp = client.post("/api/v1/execution/fills", json={
        "client_order_id": "ks-block-fill", "fill_quantity": "0.00100000", "fill_price": "99900.00",
    })
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "KILL_SWITCH_ACTIVE"


def test_kill_switch_blocks_cancel(client, approved_decision):
    _create_order(client, approved_decision["decision_id"], "ks-block-cxl")
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Test block cancel",
    })
    resp = client.post("/api/v1/execution/orders/ks-block-cxl/cancel", json={"client_order_id": "ks-block-cxl"})
    assert resp.status_code == 503


def test_kill_switch_recover_audit_event(client):
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Audit test",
    })
    aid = _create_ks_recovery_approval(client)
    client.post("/api/v1/governance/kill-switch/recover", json={
        "recovered_by": "operator", "reason": "Resolved", "approval_id": aid,
    })
    resp = client.get("/api/v1/audit/events")
    events = resp.json()
    assert any(e["event_type"] == "kill_switch.recovered" for e in events)


def test_kill_switch_trigger_audit_event(client):
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Audit trigger test",
    })
    resp = client.get("/api/v1/audit/events")
    assert any(e["event_type"] == "kill_switch.triggered" for e in resp.json())


def test_kill_switch_event_bus(client):
    from app.events.bus import event_bus
    received = []
    def handler(event):
        received.append(event)
    event_bus.subscribe("governance.kill_switch_triggered.v1", handler)
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Event test",
    })
    assert len(received) >= 1
    assert received[0].event_type == "governance.kill_switch_triggered.v1"


def test_live_switch_approved_but_still_blocked(client):
    appr = client.post("/api/v1/governance/approvals", json={
        "resource_type": "live_switch", "resource_id": "paper-main",
        "requested_by": "admin", "title": "Switch to live",
    }).json()
    client.post(f"/api/v1/governance/approvals/{appr['approval_id']}/decide", json={
        "decision": "approved", "decided_by": "admin",
    })
    # Even with approved live_switch, paper-only guard still blocks
    resp = client.post("/api/v1/orders/intents", json={
        "client_order_id": "live-approved-blocked", "account_id": "paper-main",
        "strategy_id": "trend-btc", "strategy_version": "1.0.0",
        "symbol": "BTCUSDT", "market_type": "spot", "side": "buy",
        "order_type": "limit", "quantity": "0.01000000", "limit_price": "99900.00",
        "mode": "live", "risk_decision_id": "any",
    })
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "LIVE_TRADING_NOT_ALLOWED"


# ── Paper Adapter Tests ──────────────────────────────────────────────────────

def test_adapters_list(client):
    resp = client.get("/api/v1/adapters")
    assert resp.status_code == 200
    data = resp.json()
    names = [a["name"] for a in data]
    assert "binance" in names
    assert "okx" in names
    assert "bybit" in names
    assert "paper" in names


def test_adapter_get(client):
    resp = client.get("/api/v1/adapters/binance")
    assert resp.status_code == 200
    assert resp.json()["name"] == "binance"


def test_adapter_get_not_found(client):
    resp = client.get("/api/v1/adapters/nonexistent")
    assert resp.status_code == 404


def test_adapter_connect(client):
    resp = client.post("/api/v1/adapters/binance/connect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "connected"
    assert data["exchange"] == "binance"


def test_adapter_disconnect(client):
    client.post("/api/v1/adapters/binance/connect")
    resp = client.post("/api/v1/adapters/binance/disconnect")
    assert resp.status_code == 200
    assert resp.json()["status"] == "disconnected"


def test_adapter_connect_not_found(client):
    resp = client.post("/api/v1/adapters/nonexistent/connect")
    assert resp.status_code == 404


def test_adapter_connect_kill_switch_blocks(client):
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Test block adapter",
    })
    resp = client.post("/api/v1/adapters/binance/connect")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "KILL_SWITCH_ACTIVE"


def test_adapter_symbols_disconnected(client):
    resp = client.get("/api/v1/adapters/binance/symbols")
    assert resp.status_code == 503
    data = resp.json()
    assert data["error"]["code"] == "ADAPTER_NOT_CONNECTED"
    assert "trace_id" in data["error"]


def test_adapter_ticker_disconnected(client):
    resp = client.get("/api/v1/adapters/binance/tickers/BTCUSDT")
    assert resp.status_code == 503
    data = resp.json()
    assert data["error"]["code"] == "ADAPTER_NOT_CONNECTED"
    assert "trace_id" in data["error"]


def test_adapter_symbols(client):
    client.post("/api/v1/adapters/binance/connect")
    resp = client.get("/api/v1/adapters/binance/symbols")
    assert resp.status_code == 200
    symbols = resp.json()
    assert len(symbols) >= 1
    assert symbols[0]["symbol"] == "BTCUSDT"


def test_adapter_ticker(client):
    client.post("/api/v1/adapters/binance/connect")
    resp = client.get("/api/v1/adapters/binance/tickers/BTCUSDT")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "BTCUSDT"
    assert data["last_price"] == "100000.12"


def test_adapter_ticker_not_found(client):
    client.post("/api/v1/adapters/binance/connect")
    resp = client.get("/api/v1/adapters/binance/tickers/INVALID")
    assert resp.status_code == 200


def test_adapter_connect_audit_event(client):
    client.post("/api/v1/adapters/paper/connect")
    resp = client.get("/api/v1/audit/events")
    assert any(e["event_type"] == "adapter.connected" for e in resp.json())


def test_adapter_disconnect_audit_event(client):
    client.post("/api/v1/adapters/paper/connect")
    client.post("/api/v1/adapters/paper/disconnect")
    resp = client.get("/api/v1/audit/events")
    assert any(e["event_type"] == "adapter.disconnected" for e in resp.json())


def test_adapter_event_bus(client):
    from app.events.bus import event_bus
    received = []
    def handler(event):
        received.append(event)
    event_bus.subscribe("adapter.connected.v1", handler)
    client.post("/api/v1/adapters/paper/connect")
    assert len(received) >= 1
    assert received[0].event_type == "adapter.connected.v1"


def test_adapter_trace_id_in_audit(client):
    client.post(
        "/api/v1/adapters/paper/connect",
        headers={"X-Request-ID": "adp-trace-001"},
    )
    resp = client.get("/api/v1/audit/events")
    matching = [e for e in resp.json() if e["event_type"] == "adapter.connected"]
    assert len(matching) >= 1
    assert matching[0]["trace_id"] == "adp-trace-001"


def test_paper_adapter_place_order(client):
    from app.adapters.paper_exchange_adapter import PaperExchangeAdapter
    from app.adapters.protocol import AdapterOrderStatus

    adapter = PaperExchangeAdapter("test")
    result = adapter.place_order("ord-001", "BTCUSDT", "buy", "0.01000000", "99900.00")
    assert result.client_order_id == "ord-001"
    assert result.status in (
        AdapterOrderStatus.FILLED, AdapterOrderStatus.PARTIALLY_FILLED, AdapterOrderStatus.NEW
    )


def test_paper_adapter_cancel_order(client):
    from app.adapters.paper_exchange_adapter import PaperExchangeAdapter
    from app.adapters.protocol import AdapterOrderStatus

    adapter = PaperExchangeAdapter("test")
    adapter.place_order("ord-002", "BTCUSDT", "buy", "0.01000000", "99900.00")
    result = adapter.cancel_order("ord-002")
    assert result.status == AdapterOrderStatus.CANCELLED


def test_paper_adapter_get_order_status(client):
    from app.adapters.paper_exchange_adapter import PaperExchangeAdapter
    from app.adapters.protocol import AdapterOrderStatus

    adapter = PaperExchangeAdapter("test")
    adapter.place_order("ord-003", "BTCUSDT", "buy", "0.01000000", "99900.00")
    result = adapter.get_order_status("ord-003")
    assert result.status in (
        AdapterOrderStatus.FILLED, AdapterOrderStatus.PARTIALLY_FILLED, AdapterOrderStatus.NEW
    )


def test_paper_adapter_idempotent(client):
    from app.adapters.paper_exchange_adapter import PaperExchangeAdapter

    adapter = PaperExchangeAdapter("test")
    r1 = adapter.place_order("ord-004", "BTCUSDT", "buy", "0.01000000", "99900.00")
    r2 = adapter.place_order("ord-004", "BTCUSDT", "buy", "0.01000000", "99900.00")
    # Same client_order_id returns same result (deterministic)
    assert r1.status == r2.status
    assert r1.filled_quantity == r2.filled_quantity


def test_connection_manager_connect_all(client):
    from app.adapters.connection_manager import ConnectionManager
    from app.adapters.paper_exchange_adapter import PaperExchangeAdapter

    mgr = ConnectionManager()
    mgr.register("test", PaperExchangeAdapter("test"), max_rps=50.0, max_retries=0)
    results = mgr.connect_all()
    assert len(results) == 1
    assert results[0].status.value == "connected"


def test_managed_adapter_disconnected_error(client):
    from app.adapters.connection_manager import ConnectionManager
    from app.adapters.paper_exchange_adapter import PaperExchangeAdapter
    from app.adapters.protocol import ConnectionErrorAdapter

    mgr = ConnectionManager()
    mgr.register("test", PaperExchangeAdapter("test"))
    managed = mgr.get("test")
    import pytest
    with pytest.raises(ConnectionErrorAdapter):
        managed.get_symbols()


def test_managed_adapter_connect_and_query(client):
    from app.adapters.connection_manager import ConnectionManager
    from app.adapters.paper_exchange_adapter import PaperExchangeAdapter

    mgr = ConnectionManager()
    mgr.register("test", PaperExchangeAdapter("test"))
    managed = mgr.get("test")
    managed.connect()
    symbols = managed.get_symbols()
    assert len(symbols) >= 1


def test_adapter_no_live_bypass(client):
    client.post("/api/v1/adapters/binance/connect")
    resp = client.get("/api/v1/adapters/binance/symbols")
    assert resp.status_code == 200
    # No order creation endpoint on adapters; order creation requires risk+execution
    assert resp.json()[0]["market_type"] == "spot"


# ── Adapter → Paper Execution Reconciliation Integration Tests ───────────────

def test_execute_via_adapter_success(client):
    d = _create_and_preflight(client)
    _create_order(client, d["decision_id"], "adp-exec-001")
    resp = client.post("/api/v1/execution/orders/adp-exec-001/execute")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("new", "partially_filled", "filled")
    assert data["adapter_result"]["exchange"] == "paper"
    assert data["adapter_result"]["status"] in ("new", "partially_filled", "filled")


def test_execute_via_adapter_order_not_found(client):
    resp = client.post("/api/v1/execution/orders/nonexistent/execute")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_execute_via_adapter_kill_switch_blocks(client, approved_decision):
    _create_order(client, approved_decision["decision_id"], "adp-exec-ks")
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Test block adapter exec",
    })
    resp = client.post("/api/v1/execution/orders/adp-exec-ks/execute")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "KILL_SWITCH_ACTIVE"


def test_execute_via_adapter_live_mode_blocked(client):
    resp = client.post("/api/v1/orders/intents", json={
        "client_order_id": "adp-exec-live", "account_id": "paper-main",
        "strategy_id": "trend-btc", "strategy_version": "1.0.0",
        "symbol": "BTCUSDT", "market_type": "spot", "side": "buy",
        "order_type": "limit", "quantity": "0.01000000", "limit_price": "99900.00",
        "mode": "live", "risk_decision_id": "any",
    })
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "LIVE_TRADING_NOT_ALLOWED"


def test_execute_via_adapter_idempotent(client):
    d = _create_and_preflight(client)
    _create_order(client, d["decision_id"], "adp-exec-dup")
    r1 = client.post("/api/v1/execution/orders/adp-exec-dup/execute")
    r2 = client.post("/api/v1/execution/orders/adp-exec-dup/execute")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["status"] == r2.json()["status"]
    assert r1.json()["filled_quantity"] == r2.json()["filled_quantity"]


def test_execute_via_adapter_updates_position(client):
    d = _create_and_preflight(client)
    _create_order(client, d["decision_id"], "adp-exec-pos")
    resp = client.post("/api/v1/execution/orders/adp-exec-pos/execute")
    assert resp.status_code == 200
    data = resp.json()
    if data["filled_quantity"] and float(data["filled_quantity"]) > 0:
        assert data["position_updates"] is not None
        assert data["position_updates"]["quantity"] is not None


def test_execute_via_adapter_reconciliation_consistent(client):
    d = _create_and_preflight(client)
    _create_order(client, d["decision_id"], "adp-exec-rec")
    exec_resp = client.post("/api/v1/execution/orders/adp-exec-rec/execute")
    assert exec_resp.status_code == 200
    rec_resp = client.post("/api/v1/execution/reconciliation?account_id=paper-main")
    assert rec_resp.status_code == 200
    assert rec_resp.json()["status"] in ("consistent", "discrepancy")


def test_execute_via_adapter_audit_event(client):
    d = _create_and_preflight(client)
    _create_order(client, d["decision_id"], "adp-exec-audit")
    client.post("/api/v1/execution/orders/adp-exec-audit/execute")
    resp = client.get("/api/v1/audit/events")
    matching = [e for e in resp.json() if e["resource_id"] == "adp-exec-audit"]
    assert len(matching) >= 1
    assert matching[0]["event_type"] == "order.filled"


def test_execute_via_adapter_event_bus(client):
    from app.events.bus import event_bus
    received = []
    def handler(event):
        received.append(event)
    event_bus.subscribe("order.filled.v1", handler)
    d = _create_and_preflight(client)
    _create_order(client, d["decision_id"], "adp-exec-evt")
    client.post("/api/v1/execution/orders/adp-exec-evt/execute")
    assert len(received) >= 1
    assert received[0].event_type == "order.filled.v1"
    assert received[0].payload.get("source") == "adapter"


def test_execute_via_adapter_trace_id_in_audit(client):
    d = _create_and_preflight(client)
    _create_order(client, d["decision_id"], "adp-exec-trace")
    client.post(
        "/api/v1/execution/orders/adp-exec-trace/execute",
        headers={"X-Request-ID": "adp-exec-trace-001"},
    )
    resp = client.get("/api/v1/audit/events")
    matching = [e for e in resp.json() if e["resource_id"] == "adp-exec-trace"]
    assert len(matching) >= 1
    assert matching[0]["trace_id"] == "adp-exec-trace-001"


# ── Phase 2: Versioned Strategy + Backtest Traceability Tests ───────────────

def test_strategy_create(client):
    resp = client.post("/api/v1/strategies", json={
        "strategy_id": "mom-sol", "name": "SOL Momentum", "version": "1.0.0",
        "description": "Momentum strategy", "parameters": {"rsi": 14},
        "code_ref": "git:quant-repo/strategies/mom_sol.py", "owner": "Research A", "kind": "trend",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["strategy_id"] == "mom-sol"
    assert data["code_ref"] == "git:quant-repo/strategies/mom_sol.py"
    assert data["owner"] == "Research A"
    assert data["kind"] == "trend"


def test_strategy_create_conflict(client):
    resp = client.post("/api/v1/strategies", json={
        "strategy_id": "trend-btc", "name": "Duplicate", "version": "1.0.0",
    })
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


def test_strategy_get(client):
    resp = client.get("/api/v1/strategies/trend-btc")
    assert resp.status_code == 200
    data = resp.json()
    assert data["strategy_id"] == "trend-btc"
    assert data["code_ref"] is not None


def test_strategy_get_not_found(client):
    resp = client.get("/api/v1/strategies/nonexistent")
    assert resp.status_code == 404


def test_strategy_update_version(client):
    resp = client.patch("/api/v1/strategies/trend-btc", json={
        "version": "1.1.0", "code_ref": "git:quant-repo/strategies/trend_btc_v110.py",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "1.1.0"
    assert data["code_ref"] == "git:quant-repo/strategies/trend_btc_v110.py"


def test_strategy_update_not_found(client):
    resp = client.patch("/api/v1/strategies/nonexistent", json={"version": "2.0.0"})
    assert resp.status_code == 404


def test_strategy_list_has_code_ref(client):
    resp = client.get("/api/v1/strategies")
    assert resp.status_code == 200
    strategies = resp.json()
    assert len(strategies) >= 1
    assert "code_ref" in strategies[0]
    assert strategies[0]["code_ref"] is not None


def test_strategy_audit_event(client):
    client.post("/api/v1/strategies", json={
        "strategy_id": "audit-strat", "name": "Audit Strat", "version": "1.0.0",
        "code_ref": "git:quant-repo/x.py", "owner": "researcher-x",
    })
    resp = client.get("/api/v1/audit/events")
    assert any(e["event_type"] == "strategy.created" for e in resp.json())


def test_backtest_includes_code_ref(client):
    resp = client.post("/api/v1/research/backtests", json={
        "strategy_id": "trend-btc", "strategy_version": "1.0.0", "mode": "paper",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["code_ref"] is not None
    assert data["code_ref"] == "git:quant-repo/strategies/trend_btc_v100.py"


def test_backtest_traceable_fields(client):
    resp = client.post("/api/v1/research/backtests", json={
        "strategy_id": "arb-eth", "strategy_version": "1.0.0",
        "data_snapshot": "snap_parquet_20260801", "mode": "paper",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["strategy_id"] == "arb-eth"
    assert data["strategy_version"] == "1.0.0"
    assert data["parameters"] == {"min_spread": "0.001"}
    assert data["data_snapshot"] == "snap_parquet_20260801"
    assert data["fee_model"] is not None
    assert data["slippage_model"] is not None
    assert data["run_environment"] == "paper-backtest-engine-v1"
    assert data["net_profit"] is not None
    assert data["sharpe_ratio"] is not None
    assert data["max_drawdown"] is not None
    assert data["win_rate"] is not None
    assert data["total_trades"] > 0


# ── Portfolio Target Tests ────────────────────────────────────────────────────

def test_portfolio_target_create(client):
    resp = client.post("/api/v1/portfolio/targets", json={
        "account_id": "paper-main", "strategy_id": "trend-btc",
        "strategy_version": "1.0.0", "symbol": "BTCUSDT",
        "target_quantity": "0.75000000", "target_weight": "0.40",
        "mode": "paper",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["target_quantity"] == "0.75000000"
    assert data["current_quantity"] is not None
    assert data["mode"] == "paper"
    assert data["target_id"].startswith("pt-")


def test_portfolio_target_create_with_idempotency(client):
    payload = {
        "account_id": "paper-main", "strategy_id": "trend-btc",
        "strategy_version": "1.0.0", "symbol": "BTCUSDT",
        "target_quantity": "0.60000000",
        "idempotency_key": "pt-dup-key-001",
        "mode": "paper",
    }
    r1 = client.post("/api/v1/portfolio/targets", json=payload)
    r2 = client.post("/api/v1/portfolio/targets", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["target_id"] == r2.json()["target_id"]
    assert r1.json()["idempotency_key"] == "pt-dup-key-001"


def test_portfolio_target_get(client):
    resp = client.post("/api/v1/portfolio/targets", json={
        "account_id": "paper-main", "strategy_id": "arb-eth",
        "strategy_version": "1.0.0", "symbol": "ETHUSDT",
        "target_quantity": "2.00000000", "mode": "paper",
    })
    tid = resp.json()["target_id"]
    get_resp = client.get(f"/api/v1/portfolio/targets/{tid}")
    assert get_resp.status_code == 200
    assert get_resp.json()["target_id"] == tid


def test_portfolio_target_get_not_found(client):
    resp = client.get("/api/v1/portfolio/targets/nonexistent")
    assert resp.status_code == 404


def test_portfolio_target_list(client):
    resp = client.get("/api/v1/portfolio/targets")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_portfolio_target_live_mode_blocked(client):
    resp = client.post("/api/v1/portfolio/targets", json={
        "account_id": "paper-main", "strategy_id": "trend-btc",
        "strategy_version": "1.0.0", "symbol": "BTCUSDT",
        "target_quantity": "0.50000000", "mode": "live",
    })
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "LIVE_TRADING_NOT_ALLOWED"


def test_portfolio_target_invalid_quantity(client):
    resp = client.post("/api/v1/portfolio/targets", json={
        "account_id": "paper-main", "strategy_id": "trend-btc",
        "strategy_version": "1.0.0", "symbol": "BTCUSDT",
        "target_quantity": "abc", "mode": "paper",
    })
    assert resp.status_code == 400


def test_portfolio_target_audit_event(client):
    client.post("/api/v1/portfolio/targets", json={
        "account_id": "paper-main", "strategy_id": "trend-btc",
        "strategy_version": "1.0.0", "symbol": "BTCUSDT",
        "target_quantity": "0.80000000", "mode": "paper",
    })
    resp = client.get("/api/v1/audit/events")
    assert any(e["event_type"] == "portfolio.target_created" for e in resp.json())


def test_portfolio_target_event_bus(client):
    from app.events.bus import event_bus
    received = []
    def handler(event):
        received.append(event)
    event_bus.subscribe("portfolio.target_created.v1", handler)
    client.post("/api/v1/portfolio/targets", json={
        "account_id": "paper-main", "strategy_id": "trend-btc",
        "strategy_version": "1.0.0", "symbol": "BTCUSDT",
        "target_quantity": "0.90000000", "mode": "paper",
    })
    assert len(received) >= 1
    assert received[0].event_type == "portfolio.target_created.v1"


def test_portfolio_target_trace_id(client):
    client.post(
        "/api/v1/portfolio/targets",
        json={
            "account_id": "paper-main", "strategy_id": "trend-btc",
            "strategy_version": "1.0.0", "symbol": "BTCUSDT",
            "target_quantity": "1.00000000", "mode": "paper",
        },
        headers={"X-Request-ID": "pt-trace-test"},
    )
    resp = client.get("/api/v1/audit/events")
    matching = [e for e in resp.json() if e["event_type"] == "portfolio.target_created"]
    assert len(matching) >= 1
    assert matching[0]["trace_id"] == "pt-trace-test"


def test_portfolio_target_no_order_creation(client):
    resp = client.post("/api/v1/portfolio/targets", json={
        "account_id": "paper-main", "strategy_id": "trend-btc",
        "strategy_version": "1.0.0", "symbol": "BTCUSDT",
        "target_quantity": "0.50000000", "mode": "paper",
    })
    assert resp.status_code == 201
    orders_resp = client.get("/api/v1/orders")
    assert len(orders_resp.json()) == 0


# ── Mark-to-Market PnL Tests ─────────────────────────────────────────────────

def test_mark_to_market_buy_position(client):
    resp = client.post("/api/v1/positions/mark-to-market", json={
        "account_id": "paper-main", "symbol": "BTCUSDT",
        "mark_price": "105000.00", "mode": "paper",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "BTCUSDT"
    assert data["mark_price"] == "105000.00"
    assert data["positions_updated"] >= 1
    assert len(data["updates"]) >= 1
    update = data["updates"][0]
    assert update["entry_price"] == "95000.00"  # seed position
    assert update["current_price"] == "105000.00"
    # unrealized PnL for 0.5 BTC buy at 95000, mark 105000 = (105000-95000)*0.5 = 5000
    assert update["unrealized_pnl"] == "5000.00"


def test_mark_to_market_lower_price(client):
    resp = client.post("/api/v1/positions/mark-to-market", json={
        "account_id": "paper-main", "symbol": "BTCUSDT",
        "mark_price": "90000.00", "mode": "paper",
    })
    assert resp.status_code == 200
    data = resp.json()
    # unrealized PnL = (90000-95000)*0.5 = -2500
    assert data["updates"][0]["unrealized_pnl"] == "-2500.00"


def test_mark_to_market_live_blocked(client):
    resp = client.post("/api/v1/positions/mark-to-market", json={
        "account_id": "paper-main", "symbol": "BTCUSDT",
        "mark_price": "100000.00", "mode": "live",
    })
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "LIVE_TRADING_NOT_ALLOWED"


def test_mark_to_market_invalid_price(client):
    resp = client.post("/api/v1/positions/mark-to-market", json={
        "account_id": "paper-main", "symbol": "BTCUSDT",
        "mark_price": "abc", "mode": "paper",
    })
    assert resp.status_code == 400


def test_mark_to_market_idempotent(client):
    payload = {
        "account_id": "paper-main", "symbol": "BTCUSDT",
        "mark_price": "102000.00", "mode": "paper",
        "idempotency_key": "mtm-dup-001",
    }
    r1 = client.post("/api/v1/positions/mark-to-market", json=payload)
    r2 = client.post("/api/v1/positions/mark-to-market", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["mark_price"] == r2.json()["mark_price"]


def test_mark_to_market_audit_event(client):
    client.post("/api/v1/positions/mark-to-market", json={
        "account_id": "paper-main", "symbol": "BTCUSDT",
        "mark_price": "101000.00", "mode": "paper",
    })
    resp = client.get("/api/v1/audit/events")
    assert any(e["event_type"] == "position.mtm_updated" for e in resp.json())


def test_mark_to_market_event_bus(client):
    from app.events.bus import event_bus
    received = []
    def handler(event):
        received.append(event)
    event_bus.subscribe("position.mtm_updated.v1", handler)
    client.post("/api/v1/positions/mark-to-market", json={
        "account_id": "paper-main", "symbol": "BTCUSDT",
        "mark_price": "103000.00", "mode": "paper",
    })
    assert len(received) >= 1
    assert received[0].event_type == "position.mtm_updated.v1"


def test_mark_to_market_trace_id(client):
    client.post(
        "/api/v1/positions/mark-to-market",
        json={"account_id": "paper-main", "symbol": "BTCUSDT", "mark_price": "104000.00", "mode": "paper"},
        headers={"X-Request-ID": "mtm-trace-001"},
    )
    resp = client.get("/api/v1/audit/events")
    matching = [e for e in resp.json() if e["event_type"] == "position.mtm_updated"]
    assert len(matching) >= 1
    assert matching[0]["trace_id"] == "mtm-trace-001"


def test_mark_to_market_no_order_side_effect(client):
    before = client.get("/api/v1/orders")
    before_count = len(before.json())
    client.post("/api/v1/positions/mark-to-market", json={
        "account_id": "paper-main", "symbol": "BTCUSDT",
        "mark_price": "100000.00", "mode": "paper",
    })
    after = client.get("/api/v1/orders")
    assert len(after.json()) == before_count


# ── Reconciliation Resolution Tests ──────────────────────────────────────────

def _create_discrepancy(client):
    # Seed position is 0.5 BTC with no orders → reconciliation produces discrepancy
    resp = client.post("/api/v1/execution/reconciliation?account_id=paper-main")
    assert resp.status_code == 200
    return resp.json()


def test_reconciliation_resolve_acknowledge(client):
    rec = _create_discrepancy(client)
    resp = client.post(f"/api/v1/execution/reconciliation/{rec['reconciliation_id']}/resolution", json={
        "decision": "acknowledged", "reason": "Known ledger timing gap", "actor": "ops-admin",
        "mode": "paper",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "acknowledged"
    assert data["reason"] == "Known ledger timing gap"
    assert data["actor"] == "ops-admin"
    assert data["reconciliation_id"] == rec["reconciliation_id"]
    assert data["resolution_id"].startswith("res-")


def test_reconciliation_resolve_reject(client):
    rec = _create_discrepancy(client)
    resp = client.post(f"/api/v1/execution/reconciliation/{rec['reconciliation_id']}/resolution", json={
        "decision": "rejected", "reason": "Unresolved, escalating", "actor": "risk-officer",
        "mode": "paper",
    })
    assert resp.status_code == 200
    assert resp.json()["decision"] == "rejected"


def test_reconciliation_resolve_idempotent(client):
    rec = _create_discrepancy(client)
    payload = {
        "decision": "acknowledged", "reason": "Duplicate test", "actor": "ops-admin",
        "mode": "paper", "idempotency_key": "res-dup-001",
    }
    r1 = client.post(f"/api/v1/execution/reconciliation/{rec['reconciliation_id']}/resolution", json=payload)
    r2 = client.post(f"/api/v1/execution/reconciliation/{rec['reconciliation_id']}/resolution", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["resolution_id"] == r2.json()["resolution_id"]


def test_reconciliation_resolve_invalid_id(client):
    resp = client.post("/api/v1/execution/reconciliation/nonexistent/resolution", json={
        "decision": "acknowledged", "reason": "x", "actor": "ops", "mode": "paper",
    })
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_reconciliation_resolve_live_blocked(client):
    rec = _create_discrepancy(client)
    resp = client.post(f"/api/v1/execution/reconciliation/{rec['reconciliation_id']}/resolution", json={
        "decision": "acknowledged", "reason": "x", "actor": "ops", "mode": "live",
    })
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "LIVE_TRADING_NOT_ALLOWED"


def test_reconciliation_resolve_invalid_decision(client):
    rec = _create_discrepancy(client)
    resp = client.post(f"/api/v1/execution/reconciliation/{rec['reconciliation_id']}/resolution", json={
        "decision": "invalid", "reason": "x", "actor": "ops", "mode": "paper",
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_reconciliation_resolve_audit_event(client):
    rec = _create_discrepancy(client)
    client.post(f"/api/v1/execution/reconciliation/{rec['reconciliation_id']}/resolution", json={
        "decision": "acknowledged", "reason": "audit test", "actor": "ops", "mode": "paper",
    })
    resp = client.get("/api/v1/audit/events")
    assert any(e["event_type"] == "reconciliation.resolved" for e in resp.json())


def test_reconciliation_resolve_event_bus(client):
    from app.events.bus import event_bus
    received = []
    def handler(event):
        received.append(event)
    event_bus.subscribe("reconciliation.resolved.v1", handler)
    rec = _create_discrepancy(client)
    client.post(f"/api/v1/execution/reconciliation/{rec['reconciliation_id']}/resolution", json={
        "decision": "acknowledged", "reason": "event test", "actor": "ops", "mode": "paper",
    })
    assert len(received) >= 1
    assert received[0].event_type == "reconciliation.resolved.v1"


def test_reconciliation_resolve_trace_id(client):
    rec = _create_discrepancy(client)
    client.post(
        f"/api/v1/execution/reconciliation/{rec['reconciliation_id']}/resolution",
        json={"decision": "acknowledged", "reason": "trace", "actor": "ops", "mode": "paper"},
        headers={"X-Request-ID": "res-trace-001"},
    )
    resp = client.get("/api/v1/audit/events")
    matching = [e for e in resp.json() if e["event_type"] == "reconciliation.resolved"]
    assert len(matching) >= 1
    assert matching[0]["trace_id"] == "res-trace-001"


def test_reconciliation_resolve_no_side_effect(client):
    rec = _create_discrepancy(client)
    before_pos = client.get("/api/v1/positions")
    before_orders = client.get("/api/v1/orders")
    client.post(f"/api/v1/execution/reconciliation/{rec['reconciliation_id']}/resolution", json={
        "decision": "acknowledged", "reason": "no auto-correct", "actor": "ops", "mode": "paper",
    })
    after_pos = client.get("/api/v1/positions")
    after_orders = client.get("/api/v1/orders")
    assert len(after_pos.json()) == len(before_pos.json())
    assert len(after_orders.json()) == len(before_orders.json())


# ── Kill-Switch Recovery Approval Gate Tests ─────────────────────────────────

def test_ks_recover_missing_approval(client):
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Test",
    })
    resp = client.post("/api/v1/governance/kill-switch/recover", json={
        "recovered_by": "operator", "reason": "x", "approval_id": "nonexistent",
    })
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_ks_recover_pending_approval(client):
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Test",
    })
    appr = client.post("/api/v1/governance/approvals", json={
        "resource_type": "kill_switch_recovery", "resource_id": "system",
        "requested_by": "admin", "title": "Pending approval test",
    }).json()
    resp = client.post("/api/v1/governance/kill-switch/recover", json={
        "recovered_by": "operator", "reason": "x", "approval_id": appr["approval_id"],
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "APPROVAL_PENDING"


def test_ks_recover_rejected_approval(client):
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Test",
    })
    appr = client.post("/api/v1/governance/approvals", json={
        "resource_type": "kill_switch_recovery", "resource_id": "system",
        "requested_by": "admin", "title": "Rejected approval test",
    }).json()
    client.post(f"/api/v1/governance/approvals/{appr['approval_id']}/decide", json={
        "decision": "rejected", "decided_by": "admin", "reject_reason": "Not authorized",
    })
    resp = client.post("/api/v1/governance/kill-switch/recover", json={
        "recovered_by": "operator", "reason": "x", "approval_id": appr["approval_id"],
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "APPROVAL_REJECTED"


def test_ks_recover_wrong_type_approval(client):
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Test",
    })
    appr = client.post("/api/v1/governance/approvals", json={
        "resource_type": "strategy_publish", "resource_id": "x",
        "requested_by": "admin", "title": "Wrong type",
    }).json()
    client.post(f"/api/v1/governance/approvals/{appr['approval_id']}/decide", json={
        "decision": "approved", "decided_by": "admin",
    })
    resp = client.post("/api/v1/governance/kill-switch/recover", json={
        "recovered_by": "operator", "reason": "x", "approval_id": appr["approval_id"],
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_APPROVAL_TYPE"


def test_ks_recover_duplicate_approval(client):
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Test",
    })
    aid = _create_ks_recovery_approval(client)
    r1 = client.post("/api/v1/governance/kill-switch/recover", json={
        "recovered_by": "op", "reason": "dup", "approval_id": aid,
    })
    r2 = client.post("/api/v1/governance/kill-switch/recover", json={
        "recovered_by": "op", "reason": "dup", "approval_id": aid,
    })
    assert r1.status_code == 200
    assert r1.json()["status"] == "inactive"
    # Second call: kill switch is already inactive → INVALID_STATE (not recoverable again)
    assert r2.status_code == 400
    assert r2.json()["error"]["code"] == "INVALID_STATE"


def test_ks_recover_live_blocked(client):
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Test",
    })
    aid = _create_ks_recovery_approval(client)
    resp = client.post("/api/v1/governance/kill-switch/recover", json={
        "recovered_by": "operator", "reason": "x", "approval_id": aid, "mode": "live",
    })
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "LIVE_TRADING_NOT_ALLOWED"


# ── Kill-Switch Atomicity Tests ──────────────────────────────────────────────

def test_ks_trigger_atomic(client):
    """Trigger acquires lock, state + event are atomic."""
    from app.db.memory import get_store
    store = get_store()
    ks = store.kill_switch_service
    ks.trigger("admin", "atomic test")
    state = ks.get_state()
    assert state.status.value == "active"
    assert state.triggered_by == "admin"
    assert state.trigger_reason == "atomic test"


def test_ks_recover_atomic_concurrent(client):
    """Two concurrent recovers with the same approved approval: exactly one succeeds."""
    import threading
    from app.db.memory import get_store
    from app.core.errors import QuantError

    store = get_store()
    ks = store.kill_switch_service
    svc = store.approval_service

    ks.trigger("admin", "concurrency test")
    appr = svc.create(
        resource_type="kill_switch_recovery", resource_id="system",
        requested_by="admin", title="Concurrent recovery test",
    )
    svc.decide(approval_id=appr.approval_id, decision="approved", decided_by="admin")

    results = []
    errors = []
    barrier = threading.Barrier(2)

    def do_recover():
        try:
            barrier.wait(timeout=5)
            result = ks.recover(
                recovered_by="op", reason="concurrent",
                approval_id=appr.approval_id, mode="paper",
            )
            results.append(result)
        except QuantError as e:
            errors.append(e.code)
        except Exception as e:
            errors.append(str(e))

    t1 = threading.Thread(target=do_recover)
    t2 = threading.Thread(target=do_recover)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert not t1.is_alive()
    assert not t2.is_alive()
    assert len(results) == 1
    assert len(errors) == 1
    assert errors[0] == "INVALID_STATE"
    assert results[0].status.value == "inactive"


def test_ks_recover_atomic_event_payload(client):
    """Event payload includes version=1, reason, status=inactive, resource_id/system."""
    from app.events.bus import event_bus
    received = []
    def handler(event):
        received.append(event)
    event_bus.subscribe("governance.kill_switch_recovered.v1", handler)
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Event test",
    })
    aid = _create_ks_recovery_approval(client)
    client.post("/api/v1/governance/kill-switch/recover", json={
        "recovered_by": "op", "reason": "event check", "approval_id": aid,
    })
    assert len(received) >= 1
    ev = received[0]
    assert ev.version == 1
    assert ev.resource_type == "kill_switch"
    assert ev.resource_id == "system"
    assert ev.payload["status"] == "inactive"
    assert ev.payload["reason"] == "event check"


def test_ks_recover_atomic_orders_positions_unchanged(client):
    """Recovery does not alter orders or positions."""
    before_pos = client.get("/api/v1/positions")
    before_orders = client.get("/api/v1/orders")
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Test",
    })
    aid = _create_ks_recovery_approval(client)
    client.post("/api/v1/governance/kill-switch/recover", json={
        "recovered_by": "op", "reason": "no side effect", "approval_id": aid,
    })
    after_pos = client.get("/api/v1/positions")
    after_orders = client.get("/api/v1/orders")
    assert len(after_pos.json()) == len(before_pos.json())
    assert len(after_orders.json()) == len(before_orders.json())


# ── Approval Expiry Lifecycle Tests ──────────────────────────────────────────

def test_approval_expire_due(client):
    from app.services.approval_service import ApprovalService
    from app.db.memory import get_store
    from datetime import timedelta

    store = get_store()
    svc = ApprovalService(store)
    appr = svc.create(
        resource_type="strategy_publish", resource_id="x",
        requested_by="user", title="Expiry test",
    )
    assert appr.status.value == "pending"
    far = appr.expires_at + timedelta(hours=1)
    expired = svc.expire_due(now=far)
    assert appr.approval_id in expired
    assert appr.status.value == "expired"


def test_approval_expire_due_idempotent(client):
    from app.services.approval_service import ApprovalService
    from app.db.memory import get_store
    from datetime import timedelta

    store = get_store()
    svc = ApprovalService(store)
    appr = svc.create(
        resource_type="strategy_publish", resource_id="y",
        requested_by="user", title="Idempotent expiry",
    )
    far = appr.expires_at + timedelta(hours=1)
    r1 = svc.expire_due(now=far)
    r2 = svc.expire_due(now=far)
    assert len(r1) == 1
    assert len(r2) == 0


def test_approval_expire_then_decide_blocked(client):
    from app.services.approval_service import ApprovalService
    from app.db.memory import get_store
    from datetime import timedelta
    import pytest

    store = get_store()
    svc = ApprovalService(store)
    appr = svc.create(
        resource_type="strategy_publish", resource_id="z",
        requested_by="user", title="Blocked decide",
    )
    far = appr.expires_at + timedelta(hours=1)
    svc.expire_due(now=far)
    from app.core.errors import QuantError
    with pytest.raises(QuantError) as exc:
        svc.decide(approval_id=appr.approval_id, decision="approved", decided_by="admin")
    assert exc.value.code == "APPROVAL_EXPIRED"


def test_approval_expire_due_event_bus(client):
    from app.events.bus import event_bus
    from app.services.approval_service import ApprovalService
    from app.db.memory import get_store
    from datetime import timedelta

    received = []
    def handler(event):
        received.append(event)
    event_bus.subscribe("governance.approval_expired.v1", handler)
    store = get_store()
    svc = ApprovalService(store)
    appr = svc.create(
        resource_type="strategy_publish", resource_id="b",
        requested_by="user", title="Event bus expiry",
    )
    far = appr.expires_at + timedelta(hours=1)
    svc.expire_due(now=far)
    assert len(received) >= 1
    assert received[0].event_type == "governance.approval_expired.v1"
    assert len(received) >= 1
    ev = received[0]
    assert ev.event_type == "governance.approval_expired.v1"
    assert ev.version == 1
    assert ev.resource_type == "approval"
    assert ev.resource_id == appr.approval_id
    assert ev.actor == "system"
    assert ev.payload["approval_id"] == appr.approval_id
    assert ev.payload["resource_type"] == "strategy_publish"
    assert ev.payload["resource_id"] == "b"
    assert ev.payload["status"] == "expired"
    assert ev.payload["expired_at"]


def test_approval_expired_kill_switch_recovery_blocked(client):
    from app.services.approval_service import ApprovalService
    from app.db.memory import get_store
    from datetime import timedelta

    store = get_store()
    svc = ApprovalService(store)
    appr = svc.create(
        resource_type="kill_switch_recovery", resource_id="system",
        requested_by="admin", title="KS recovery expiry",
    )
    client.post("/api/v1/governance/kill-switch/trigger", json={
        "triggered_by": "admin", "reason": "Test",
    })
    far = appr.expires_at + timedelta(hours=1)
    svc.expire_due(now=far)
    resp = client.post("/api/v1/governance/kill-switch/recover", json={
        "recovered_by": "operator", "reason": "x", "approval_id": appr.approval_id, "mode": "paper",
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "APPROVAL_EXPIRED"
    # kill-switch remains active
    ks = client.get("/api/v1/governance/kill-switch")
    assert ks.json()["status"] == "active"


def test_approval_list_refreshes_expiry(client):
    from app.services.approval_service import ApprovalService
    from app.db.memory import get_store
    from datetime import timedelta

    store = get_store()
    svc = ApprovalService(store)
    appr = svc.create(
        resource_type="strategy_publish", resource_id="c",
        requested_by="user", title="List refresh",
    )
    far = appr.expires_at + timedelta(hours=1)
    svc.expire_due(now=far)
    approvals = svc.list_approvals()
    expired = [a for a in approvals if a.status.value == "expired"]
    assert len(expired) >= 1
    assert any(a.approval_id == appr.approval_id for a in expired)


def test_approval_get_refreshes_expiry(client):
    from app.services.approval_service import ApprovalService
    from app.db.memory import get_store
    from datetime import timedelta

    store = get_store()
    svc = ApprovalService(store)
    appr = svc.create(
        resource_type="strategy_publish", resource_id="d",
        requested_by="user", title="Get refresh",
    )
    far = appr.expires_at + timedelta(hours=1)
    svc.expire_due(now=far)
    fetched = svc.get_approval(appr.approval_id)
    assert fetched is not None
    assert fetched.status.value == "expired"


def test_approval_expiry_projects_versioned_audit_event(client):
    from app.db.memory import get_store
    from datetime import timedelta

    store = get_store()
    svc = store.approval_service
    approval = svc.create(
        resource_type="strategy_publish", resource_id="audit-projection",
        requested_by="researcher", title="Audit projection",
    )
    orders_before = len(store.orders)
    positions_before = len(store.positions)

    expired = svc.expire_due(now=approval.expires_at + timedelta(seconds=1))

    assert expired == [approval.approval_id]
    audit = client.get("/api/v1/audit/events")
    assert audit.status_code == 200
    matching = [e for e in audit.json() if e["event_type"] == "governance.approval_expired.v1"]
    matching = [e for e in matching if e["resource_id"] == approval.approval_id]
    assert len(matching) == 1
    event = matching[0]
    assert event["actor"] == "system"
    assert event["resource_type"] == "approval"
    assert event["details"]["version"] == 1
    assert event["details"]["payload"] == {
        "approval_id": approval.approval_id,
        "resource_type": "strategy_publish",
        "resource_id": "audit-projection",
        "status": "expired",
        "expired_at": approval.expires_at.isoformat(),
    }
    assert len(store.orders) == orders_before
    assert len(store.positions) == positions_before


def test_approval_expiry_audit_projection_is_idempotent_for_lazy_refresh(client):
    from app.db.memory import get_store
    from app.models.domain import utcnow
    from datetime import timedelta

    store = get_store()
    svc = store.approval_service
    approval = svc.create(
        resource_type="strategy_publish", resource_id="lazy-audit",
        requested_by="researcher", title="Lazy audit projection",
    )
    approval.expires_at = utcnow() - timedelta(seconds=1)

    assert svc.get_approval(approval.approval_id).status.value == "expired"
    assert svc.get_approval(approval.approval_id).status.value == "expired"
    assert any(a.approval_id == approval.approval_id for a in svc.list_approvals())

    audit = client.get("/api/v1/audit/events")
    matching = [
        e for e in audit.json()
        if e["event_type"] == "governance.approval_expired.v1"
        and e["resource_id"] == approval.approval_id
    ]
    assert len(matching) == 1
    assert matching[0]["details"]["payload"]["status"] == "expired"
