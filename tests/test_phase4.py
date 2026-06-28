"""Tests for Phase 4 production depth features."""
import pytest
from fastapi.testclient import TestClient

from grc_dashboard.api.main import app
from grc_dashboard.compliance.cross_framework import load_cross_framework_map
from grc_dashboard.db.session import init_db


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    await init_db()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Tenant-ID": "demo-global-hq"}


def _login(client: TestClient, username: str = "admin") -> str:
    passwords = {"admin": "valence123", "auditor": "auditor123"}
    res = client.post("/api/auth/login", json={"username": username, "password": passwords[username]})
    assert res.status_code == 200
    return res.json()["access_token"]


def test_training_courses():
    with TestClient(app) as client:
        token = _login(client)
        res = client.get("/api/training/courses", headers=_headers(token))
        assert res.status_code == 200
        assert len(res.json()) >= 1


def test_intelligence_gaps():
    with TestClient(app) as client:
        token = _login(client)
        res = client.get("/api/intelligence/gaps", headers=_headers(token))
        assert res.status_code == 200
        body = res.json()
        assert "prioritized_gaps" in body
        assert "executive_summary" in body


def test_cross_framework_map():
    unified = load_cross_framework_map()
    assert len(unified) >= 5


def test_cross_framework_api():
    with TestClient(app) as client:
        token = _login(client, "auditor")
        res = client.get("/api/compliance/cross-framework", headers=_headers(token))
        assert res.status_code == 200
        assert res.json()["total_unified"] >= 1


def test_vendor_breach_alerts():
    with TestClient(app) as client:
        token = _login(client)
        res = client.get("/api/vendors/breaches", headers=_headers(token))
        assert res.status_code == 200
        assert isinstance(res.json(), list)
