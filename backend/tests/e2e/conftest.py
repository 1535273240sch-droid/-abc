"""Global Fixtures and Configuration for 4-Tier E2E Testing Suite.

Provides HTTP client fixtures (live backend and Nginx reverse proxy),
JWT authentication tokens for standard roles, test database/memory isolation helpers,
and reusable preflight & trading fixtures.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from typing import Any, Generator

import httpx
import pytest
from fastapi.testclient import TestClient

# Ensure backend root is in sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.auth import create_access_token
from app.core.config import settings
from app.main import app

LIVE_BASE_URL = os.environ.get("QUANT_E2E_LIVE_URL", "http://127.0.0.1:8000")
NGINX_BASE_URL = os.environ.get("QUANT_E2E_NGINX_URL", "http://127.0.0.1")


@pytest.fixture(scope="session")
def live_url() -> str:
    return LIVE_BASE_URL


@pytest.fixture(scope="session")
def nginx_url() -> str:
    return NGINX_BASE_URL


@pytest.fixture(scope="session")
def live_client() -> Generator[httpx.Client, None, None]:
    """HTTP Client connected directly to FastAPI backend (127.0.0.1:8000)."""
    with httpx.Client(base_url=LIVE_BASE_URL, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="session")
def nginx_client() -> Generator[httpx.Client, None, None]:
    """HTTP Client connected to Nginx reverse proxy (127.0.0.1:80)."""
    with httpx.Client(base_url=NGINX_BASE_URL, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="function")
def test_client() -> Generator[TestClient, None, None]:
    """In-process TestClient for isolated internal unit/integration contracts."""
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="session")
def auth_tokens() -> dict[str, str]:
    """Generate standard JWT tokens for key RBAC roles."""
    roles = ["admin", "trader", "risk_admin", "auditor", "viewer", "quant", "risk_officer"]
    tokens = {}
    for role in roles:
        token = str(create_access_token(f"user-{role}", role=role))
        tokens[role] = token
    return tokens


@pytest.fixture(scope="session")
def auth_headers(auth_tokens: dict[str, str]):
    """Helper function to construct Authorization headers for any role."""
    def _headers(role: str = "admin") -> dict[str, str]:
        token = auth_tokens.get(role, auth_tokens["admin"])
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    return _headers


@pytest.fixture(scope="function")
def unique_account_id() -> str:
    """Generate an isolated unique account ID per test."""
    return f"e2e-acc-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="function")
def approved_preflight(live_client: httpx.Client, auth_headers, unique_account_id: str) -> dict[str, Any]:
    """Create an approved risk decision for order submission."""
    resp = live_client.post(
        "/api/v1/risk/preflight",
        json={
            "account_id": unique_account_id,
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.01000000",
            "price": "65000.00",
            "strategy_id": "trend-btc",
            "strategy_version": "1.0.0",
            "mode": "paper",
        },
        headers=auth_headers("trader"),
    )
    assert resp.status_code == 200, f"Preflight failed: {resp.text}"
    data = resp.json()
    data["account_id"] = unique_account_id
    return data


@pytest.fixture(autouse=True)
def ensure_clean_kill_switch(live_client: httpx.Client, auth_headers):
    """Ensure kill-switch is inactive before each test."""
    try:
        status_resp = live_client.get("/api/v1/governance/kill-switch")
        if status_resp.status_code == 200:
            ks_data = status_resp.json()
            if ks_data.get("status") == "active":
                appr_resp = live_client.post(
                    "/api/v1/governance/approvals",
                    json={
                        "resource_type": "kill_switch_recovery",
                        "resource_id": "system_emergency",
                        "requested_by": "admin_cleanup",
                        "title": "Auto Recovery for Tests",
                        "details": "Automated cleanup recovering kill switch",
                    },
                    headers=auth_headers("admin"),
                )
                if appr_resp.status_code in (200, 201):
                    appr_id = appr_resp.json()["approval_id"]
                    live_client.post(
                        f"/api/v1/governance/approvals/{appr_id}/decide",
                        json={"decision": "approved", "decided_by": "admin", "reject_reason": None},
                        headers=auth_headers("risk_admin"),
                    )
                    live_client.post(
                        "/api/v1/governance/kill-switch/recover",
                        json={"recovered_by": "admin", "reason": "test fixture cleanup", "approval_id": appr_id, "mode": "paper"},
                        headers=auth_headers("admin"),
                    )
    except Exception:
        pass
    yield
