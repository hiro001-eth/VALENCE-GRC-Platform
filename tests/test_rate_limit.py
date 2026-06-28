"""Tests for login rate limiting and account lockout."""
import pytest
from fastapi.testclient import TestClient

from grc_dashboard.api.main import app
from grc_dashboard.auth import rate_limit


@pytest.fixture(autouse=True)
def reset_rate_limit_state(monkeypatch):
    """Isolate tests from Redis and in-memory counters."""
    monkeypatch.setattr(rate_limit, "LOGIN_RATE_LIMIT", 100)
    monkeypatch.setattr(rate_limit, "LOCKOUT_THRESHOLD", 3)
    rate_limit._memory_counters.clear()
    monkeypatch.setattr(rate_limit.session_store, "_redis_client", None)
    yield
    rate_limit._memory_counters.clear()


def test_account_lockout_after_failed_attempts():
    with TestClient(app) as client:
        for _ in range(3):
            res = client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "wrong"},
            )
            assert res.status_code == 401

        locked = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert locked.status_code == 423


def test_successful_login_clears_lockout_counter():
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})

        ok = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "valence123"},
        )
        assert ok.status_code == 200

        bad = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert bad.status_code == 401


def test_sandbox_info_endpoint():
    with TestClient(app) as client:
        res = client.get("/api/auth/sandbox-info")
        assert res.status_code == 200
        data = res.json()
        assert "show_credential_hints" in data
        assert "password" not in res.text.lower() or "rotated" in res.text.lower()
