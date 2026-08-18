"""Tests for billing entitlements and OAuth production guards."""
from __future__ import annotations

import pytest

from grc_dashboard.billing.entitlements import plan_limits, subscription_allows_access
from grc_dashboard.db.models import Tenant
from grc_dashboard.integrations.oauth import start_oauth_flow


def test_plan_limits_starter() -> None:
    limits = plan_limits("starter")
    assert limits["seats"] == 10
    assert limits["frameworks"] == 2


def test_demo_tenant_always_allowed() -> None:
    tenant = Tenant(id="demo", name="Demo", industry="", region="", is_demo=True, subscription_status="cancelled")
    assert subscription_allows_access(tenant) is True


def test_oauth_demo_mode_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.setenv("VALENCE_ENV", "development")
    result = start_oauth_flow("tenant-1", "github", "admin")
    assert result.get("demo_connect") is True


def test_oauth_blocks_demo_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GITHUB_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("VALENCE_ENV", "production")
    monkeypatch.setenv("VALENCE_ALLOW_DEMO_OAUTH", "false")
    with pytest.raises(ValueError, match="Live OAuth required"):
        start_oauth_flow("tenant-1", "github", "admin")
