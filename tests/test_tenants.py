"""Tests for tenant registration and demo sandbox access."""
import pytest
from fastapi.testclient import TestClient

from grc_dashboard.api.main import app
from grc_dashboard.db.session import init_db


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    await init_db()


def test_register_organization(unique_registration_payload):
    with TestClient(app) as client:
        res = client.post(
            "/api/tenants/register",
            json=unique_registration_payload,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["admin_username"] == unique_registration_payload["admin_username"]


def test_demo_tenants_public():
    with TestClient(app) as client:
        res = client.get("/api/tenants/demo")
        assert res.status_code == 200
        tenants = res.json()
        assert len(tenants) == 4
        ids = {t["tenant_id"] for t in tenants}
        assert "demo-global-hq" in ids
        assert "demo-healthcare" in ids


def test_tenant_header_enforced_for_production_user(unique_registration_payload):
    with TestClient(app) as client:
        login = client.post(
            "/api/tenants/register",
            json=unique_registration_payload,
        )
        assert login.status_code == 201
        tenant_id = login.json()["tenant_id"]

        auth = client.post(
            "/api/auth/login",
            json={
                "username": unique_registration_payload["admin_username"],
                "password": unique_registration_payload["admin_password"],
            },
        )
        token = auth.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": "demo-global-hq"}
        res = client.get("/api/metrics/", headers=headers)
        assert res.status_code == 403

        headers["X-Tenant-ID"] = tenant_id
        res = client.get("/api/metrics/", headers=headers)
        assert res.status_code == 200
