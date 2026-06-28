import os

import pytest

from grc_dashboard.auth.sso import (
    is_sso_configured,
    load_sso_config,
    map_role_from_claims,
    profile_from_claims,
    provider_setup_guide,
    resolve_issuer_url,
    sso_setup_hint,
)


@pytest.fixture(autouse=True)
def clear_sso_env(monkeypatch):
    keys = [
        "AUTH_SSO_ENABLED",
        "AUTH_SSO_PROVIDER",
        "AUTH_AZURE_TENANT_ID",
        "AUTH_OKTA_DOMAIN",
        "AUTH_OKTA_AUTH_SERVER",
        "AUTH_OIDC_CLIENT_ID",
        "AUTH_OIDC_CLIENT_SECRET",
        "AUTH_OIDC_ISSUER_URL",
        "AUTH_OIDC_REDIRECT_URI",
        "AUTH_SSO_GROUP_ROLE_MAP",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_resolve_azure_issuer_from_tenant_id(monkeypatch):
    monkeypatch.setenv("AUTH_AZURE_TENANT_ID", "11111111-2222-3333-4444-555555555555")
    issuer = resolve_issuer_url("azure")
    assert issuer == "https://login.microsoftonline.com/11111111-2222-3333-4444-555555555555/v2.0"


def test_resolve_okta_issuer_from_domain(monkeypatch):
    monkeypatch.setenv("AUTH_OKTA_DOMAIN", "dev-12345.okta.com")
    monkeypatch.setenv("AUTH_OKTA_AUTH_SERVER", "default")
    issuer = resolve_issuer_url("okta")
    assert issuer == "https://dev-12345.okta.com/oauth2/default"


def test_load_sso_config_azure_preset(monkeypatch):
    monkeypatch.setenv("AUTH_SSO_ENABLED", "true")
    monkeypatch.setenv("AUTH_SSO_PROVIDER", "azure")
    monkeypatch.setenv("AUTH_AZURE_TENANT_ID", "tenant-guid")
    monkeypatch.setenv("AUTH_OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("AUTH_OIDC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("AUTH_OIDC_REDIRECT_URI", "https://app.example.com/api/auth/sso/callback")

    config = load_sso_config()
    assert is_sso_configured(config)
    assert config.provider == "azure"
    assert "login.microsoftonline.com" in config.issuer_url
    assert config.scopes == "openid profile email"


def test_sso_setup_hint_when_enabled_but_incomplete(monkeypatch):
    monkeypatch.setenv("AUTH_SSO_ENABLED", "true")
    monkeypatch.setenv("AUTH_SSO_PROVIDER", "azure")
    config = load_sso_config()
    hint = sso_setup_hint(config)
    assert hint is not None
    assert "AUTH_OIDC_CLIENT_ID" in hint


def test_group_role_mapping(monkeypatch):
    monkeypatch.setenv(
        "AUTH_SSO_GROUP_ROLE_MAP",
        "Valence-Admins:admin,Valence-Auditors:auditor",
    )
    config = load_sso_config()
    role = map_role_from_claims(
        {"groups": ["Valence-Auditors"]},
        "analyst",
        config.group_role_map,
    )
    assert role == "auditor"


def test_profile_from_claims_azure_upn():
    profile = profile_from_claims(
        {
            "name": "Jane Doe",
            "preferred_username": "jane.doe@contoso.com",
            "roles": ["analyst"],
        },
        "auditor",
    )
    assert profile["username"] == "jane.doe"
    assert profile["email"] == "jane.doe@contoso.com"
    assert profile["role"] == "analyst"


def test_provider_setup_guide_includes_azure_steps():
    guide = provider_setup_guide("azure")
    assert guide["provider"] == "Microsoft Entra ID (Azure AD)"
    assert any("AUTH_AZURE_TENANT_ID" in item for item in guide["required_env"])
