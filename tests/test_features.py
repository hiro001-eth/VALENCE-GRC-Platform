"""Tests for feature resolution and team access."""
from grc_dashboard.auth.features import (
    DEPARTMENT_PRESETS,
    has_feature,
    resolve_features,
)


def test_grc_department_preset():
    features = resolve_features("analyst", "grc", None)
    assert features["compliance"] is True
    assert features["threat_intel"] is False
    assert "compliance" in DEPARTMENT_PRESETS["grc"]


def test_soc_department_preset():
    features = resolve_features("analyst", "soc", None)
    assert features["threat_intel"] is True
    assert features["compliance"] is False


def test_custom_feature_override():
    features = resolve_features("analyst", "soc", ["dashboard", "benchmarking"])
    assert features["benchmarking"] is True
    assert features["threat_intel"] is False


def test_admin_has_team_admin():
    assert has_feature("admin", "general", None, "team_admin") is True


def test_auditor_no_team_admin():
    assert has_feature("auditor", "grc", None, "team_admin") is False
