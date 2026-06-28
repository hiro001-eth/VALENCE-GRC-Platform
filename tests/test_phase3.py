"""Tests for Phase 3 compliance depth features."""
import pytest
from fastapi.testclient import TestClient

from grc_dashboard.api.main import app
from grc_dashboard.compliance.framework_loader import FrameworkLoader
from grc_dashboard.db.session import init_db


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    await init_db()


def _headers(token: str, tenant: str = "demo-global-hq") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant}


def _login(client: TestClient, username: str = "admin") -> str:
    passwords = {"admin": "valence123", "auditor": "auditor123"}
    res = client.post("/api/auth/login", json={"username": username, "password": passwords.get(username, "valence123")})
    assert res.status_code == 200
    return res.json()["access_token"]


def test_policies_list():
    with TestClient(app) as client:
        token = _login(client)
        res = client.get("/api/policies/", headers=_headers(token))
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 1
        assert "title" in data[0]


def test_auditor_dashboard():
    with TestClient(app) as client:
        token = _login(client, "auditor")
        res = client.get("/api/auditor/dashboard", headers=_headers(token))
        assert res.status_code == 200
        body = res.json()
        assert "readiness" in body
        assert body["access_scope"] == "read_only"


def test_hipaa_gdpr_frameworks_loaded():
    frameworks = FrameworkLoader().list_frameworks()
    assert "HIPAA" in frameworks
    assert "GDPR" in frameworks
    assert len(FrameworkLoader().load_framework("SOC2").controls) >= 40


def test_personnel_jml():
    with TestClient(app) as client:
        token = _login(client)
        res = client.get("/api/personnel/", headers=_headers(token))
        assert res.status_code == 200
        assert len(res.json()) >= 1


def test_questionnaire_auto_fill():
    with TestClient(app) as client:
        token = _login(client)
        res = client.post("/api/questionnaires/auto-fill", headers=_headers(token))
        assert res.status_code == 200
        assert "responses" in res.json()
