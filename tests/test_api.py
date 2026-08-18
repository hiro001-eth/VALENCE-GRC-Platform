import pytest
from fastapi.testclient import TestClient

from grc_dashboard.api.main import app
from grc_dashboard.db.session import init_db


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    # Initialize the test database / seed users
    await init_db()


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_auth_login_success():
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "valence123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "admin"


def test_auth_login_invalid():
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong_password"},
        )
        assert response.status_code == 401


def test_rbac_restrictions():
    with TestClient(app) as client:
        # Login as auditor (role: auditor)
        login_response = client.post(
            "/api/auth/login",
            json={"username": "auditor", "password": "auditor123"},
        )
        assert login_response.status_code == 200
        auditor_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {auditor_token}"}

        # Auditor can read metrics
        metrics_response = client.get("/api/metrics/", headers=headers)
        assert metrics_response.status_code == 200

        # Auditor cannot generate reports (requires analyst or admin)
        reports_response = client.post(
            "/api/reports/generate",
            headers=headers,
            json={"title": "Audit Report"},
        )
        assert reports_response.status_code == 403


def test_websocket_stream():
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "valence123"},
        )
        token = login.json()["access_token"]
        with client.websocket_connect(f"/ws/live?token={token}") as websocket:
            data = websocket.receive_json()
            assert data["type"] == "metrics_update"
            websocket.send_text("ping")
            data = websocket.receive_json()
            assert data["type"] == "pong"
