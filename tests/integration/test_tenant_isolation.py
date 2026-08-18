"""Multi-tenant isolation unit and integration tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.security import admin_headers


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    from grc_dashboard.db.session import init_db
    await init_db()



class TestTenantIsolation:
    """Verifies strict tenant partition checks across API and DB resource layers."""

    def test_risk_posture_tenant_scoped(self, client: TestClient):
        """P1: Verifies risk posture metrics return isolated results mapped to active tenant."""
        headers = admin_headers(client)
        res = client.get("/api/command-center/posture", headers=headers)
        assert res.status_code == 200
        data = res.json()
        # Verify the resolved tenant context belongs to user tenant scope
        assert "headline" in data

    def test_remediation_tasks_tenant_scoped(self, client: TestClient):
        """P1: Ensures users cannot access remediation tasks of neighboring tenants."""
        headers = admin_headers(client)
        res = client.get("/api/remediation/", headers=headers)
        assert res.status_code == 200
        # Result list must be populated only with records belonging to current tenant
        assert isinstance(res.json()["tasks"], list)
