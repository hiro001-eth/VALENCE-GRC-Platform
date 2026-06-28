"""Tests for production configuration validation."""
import os

import pytest

from grc_dashboard.deployment import production as prod


def test_collect_readiness_development():
    report = prod.collect_readiness()
    assert "checks" in report
    assert report["environment"] in {"development", "test", "testing"}


def test_production_blocks_default_jwt(monkeypatch):
    monkeypatch.setenv("VALENCE_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "valence-grc-enterprise-secret-CHANGE-IN-PRODUCTION-minimum-32-chars")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/valence")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("VALENCE_SHOW_DEMO_CREDENTIALS", "false")
    monkeypatch.setattr(prod, "IS_TESTING", False)
    monkeypatch.setattr(prod, "IS_PRODUCTION", True)
    monkeypatch.setattr(prod, "VALENCE_ENV", "production")

    with pytest.raises(SystemExit):
        prod.validate_production_startup()


def test_production_passes_with_valid_config(monkeypatch):
    monkeypatch.setenv("VALENCE_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/valence")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://grc.acme-security.io")
    monkeypatch.setenv("VALENCE_PUBLIC_URL", "https://grc.acme-security.io")
    monkeypatch.setenv("VALENCE_SHOW_DEMO_CREDENTIALS", "false")
    monkeypatch.setattr(prod, "IS_TESTING", False)
    monkeypatch.setattr(prod, "IS_PRODUCTION", True)
    monkeypatch.setattr(prod, "VALENCE_ENV", "production")

    prod.validate_production_startup()
    report = prod.collect_readiness()
    assert report["production_ready"] is True
