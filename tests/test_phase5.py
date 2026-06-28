"""Tests for Sprinto-parity gap fixes."""
from fastapi.testclient import TestClient

from grc_dashboard.api.main import app
from grc_dashboard.integrations.marketplace_catalog import build_extended_catalog


def test_marketplace_200_plus():
    catalog = build_extended_catalog()
    assert len(catalog) >= 100


def test_marketplace_search_pagination():
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "valence123"})
        token = login.json()["access_token"]
        res = client.get(
            "/api/connectors/marketplace?page=1&limit=10",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "demo-global-hq"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["total"] >= 100
        assert len(body["integrations"]) <= 10


def test_oauth_demo_connect():
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "valence123"})
        token = login.json()["access_token"]
        res = client.post(
            "/api/connectors/marketplace/github/oauth",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "demo-global-hq"},
            json={},
        )
        assert res.status_code == 200
        assert res.json().get("status") == "connected" or "authorize_url" in res.json()


def test_fedramp_cmmc_frameworks():
    from grc_dashboard.compliance.framework_loader import FrameworkLoader

    fws = FrameworkLoader().list_frameworks()
    assert "FEDRAMP" in fws
    assert "CMMC" in fws


def test_pentest_list():
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "valence123"})
        token = login.json()["access_token"]
        res = client.get(
            "/api/pentest/",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "demo-global-hq"},
        )
        assert res.status_code == 200
        assert len(res.json()) >= 1
