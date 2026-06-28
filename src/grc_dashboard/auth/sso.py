"""OIDC / SSO authentication helpers (Azure Entra ID, Okta, and generic providers)."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog
from jose import jwt

logger = structlog.get_logger(__name__)

# Short-lived codes exchanged by the SPA after SSO redirect.
_SSO_CODE_TTL_SECONDS = 60
_SSO_STATE_TTL_SECONDS = 600
_SSO_CODE_PREFIX = "valence:sso:exchange:"
_SSO_STATE_PREFIX = "valence:sso:state:"

_PROVIDER_DEFAULT_SCOPES = {
    "azure": "openid profile email",
    "okta": "openid profile email groups",
    "oidc": "openid profile email",
}


@dataclass(frozen=True)
class SSOConfig:
    enabled: bool
    provider: str
    client_id: str
    client_secret: str
    issuer_url: str
    redirect_uri: str
    default_role: str
    scopes: str
    group_role_map: dict[str, str]


@dataclass(frozen=True)
class OIDCDiscovery:
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str | None


def resolve_issuer_url(provider: str, issuer: str = "") -> str:
    """Build issuer URL from provider presets when AUTH_OIDC_ISSUER_URL is omitted."""
    if issuer:
        return issuer.rstrip("/")

    provider_key = provider.lower()
    if provider_key == "azure":
        tenant_id = os.getenv("AUTH_AZURE_TENANT_ID", "").strip()
        if tenant_id:
            return f"https://login.microsoftonline.com/{tenant_id}/v2.0"
    if provider_key == "okta":
        domain = os.getenv("AUTH_OKTA_DOMAIN", "").strip()
        auth_server = os.getenv("AUTH_OKTA_AUTH_SERVER", "default").strip() or "default"
        if domain:
            domain = domain.removeprefix("https://").removeprefix("http://").rstrip("/")
            return f"https://{domain}/oauth2/{auth_server}"
    return ""


def _load_group_role_map() -> dict[str, str]:
    """Map IdP group/app-role names to VALENCE roles.

    Format: ``AdminGroup:admin,CISO Group:ciso,Everyone:analyst``
    """
    raw = os.getenv("AUTH_SSO_GROUP_ROLE_MAP", "").strip()
    if not raw:
        return {}

    mapping: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        group_name, role = entry.split(":", 1)
        role = role.strip().lower()
        if role in {"admin", "ciso", "analyst", "auditor"}:
            mapping[group_name.strip().lower()] = role
    return mapping


def load_sso_config() -> SSOConfig:
    provider = os.getenv("AUTH_SSO_PROVIDER", "azure").lower()
    issuer = resolve_issuer_url(provider, os.getenv("AUTH_OIDC_ISSUER_URL", ""))
    default_scopes = _PROVIDER_DEFAULT_SCOPES.get(provider, _PROVIDER_DEFAULT_SCOPES["oidc"])

    return SSOConfig(
        enabled=os.getenv("AUTH_SSO_ENABLED", "false").lower() in {"1", "true", "yes"},
        provider=provider,
        client_id=os.getenv("AUTH_OIDC_CLIENT_ID", ""),
        client_secret=os.getenv("AUTH_OIDC_CLIENT_SECRET", ""),
        issuer_url=issuer,
        redirect_uri=os.getenv(
            "AUTH_OIDC_REDIRECT_URI",
            "http://localhost:8000/api/auth/sso/callback",
        ),
        default_role=os.getenv("AUTH_SSO_DEFAULT_ROLE", "analyst"),
        scopes=os.getenv("AUTH_OIDC_SCOPES", default_scopes),
        group_role_map=_load_group_role_map(),
    )


def is_sso_configured(config: SSOConfig) -> bool:
    return bool(
        config.enabled
        and config.client_id
        and config.client_secret
        and config.issuer_url
        and config.redirect_uri
    )


def sso_setup_hint(config: SSOConfig) -> str | None:
    """Return a short operator hint when SSO is enabled but misconfigured."""
    if not config.enabled:
        return None
    missing = []
    if not config.client_id:
        missing.append("AUTH_OIDC_CLIENT_ID")
    if not config.client_secret:
        missing.append("AUTH_OIDC_CLIENT_SECRET")
    if not config.issuer_url:
        if config.provider == "azure":
            missing.append("AUTH_AZURE_TENANT_ID or AUTH_OIDC_ISSUER_URL")
        elif config.provider == "okta":
            missing.append("AUTH_OKTA_DOMAIN or AUTH_OIDC_ISSUER_URL")
        else:
            missing.append("AUTH_OIDC_ISSUER_URL")
    if not config.redirect_uri:
        missing.append("AUTH_OIDC_REDIRECT_URI")
    if not missing:
        return None
    return f"SSO enabled but missing: {', '.join(missing)}"


async def discover_oidc(config: SSOConfig) -> OIDCDiscovery:
    discovery_url = f"{config.issuer_url}/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(discovery_url)
        response.raise_for_status()
        data = response.json()

    return OIDCDiscovery(
        authorization_endpoint=data["authorization_endpoint"],
        token_endpoint=data["token_endpoint"],
        userinfo_endpoint=data.get("userinfo_endpoint"),
    )


def build_authorization_url(
    discovery: OIDCDiscovery,
    config: SSOConfig,
    state: str,
    nonce: str,
) -> str:
    params = {
        "client_id": config.client_id,
        "response_type": "code",
        "redirect_uri": config.redirect_uri,
        "response_mode": "query",
        "scope": config.scopes,
        "state": state,
        "nonce": nonce,
    }
    return f"{discovery.authorization_endpoint}?{urlencode(params)}"


def _claims_from_id_token(id_token: str, expected_nonce: str | None = None) -> dict[str, Any]:
    claims: dict[str, Any] = jwt.get_unverified_claims(id_token)
    if expected_nonce and claims.get("nonce") != expected_nonce:
        raise ValueError("OIDC nonce mismatch")
    return claims


async def exchange_code_for_userinfo(
    discovery: OIDCDiscovery,
    config: SSOConfig,
    code: str,
    expected_nonce: str | None = None,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        token_response = await client.post(
            discovery.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "code": code,
                "redirect_uri": config.redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_response.raise_for_status()
        token_data = token_response.json()
        access_token = token_data.get("access_token")
        id_token = token_data.get("id_token")
        if not access_token and not id_token:
            raise ValueError("OIDC provider did not return tokens")

        id_claims = _claims_from_id_token(id_token, expected_nonce) if id_token else {}

        if discovery.userinfo_endpoint and access_token:
            userinfo_response = await client.get(
                discovery.userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            userinfo_response.raise_for_status()
            userinfo = userinfo_response.json()
            return {**id_claims, **userinfo}

        if id_claims:
            return id_claims

        raise ValueError("OIDC provider did not return user profile data")


def store_sso_exchange(payload: dict[str, Any]) -> str:
    from grc_dashboard.cache import session_store

    code = secrets.token_urlsafe(32)
    session_store.set_json(f"{_SSO_CODE_PREFIX}{code}", payload, _SSO_CODE_TTL_SECONDS)
    return code


def pop_sso_exchange(code: str) -> dict[str, Any] | None:
    from grc_dashboard.cache import session_store

    return session_store.get_json(f"{_SSO_CODE_PREFIX}{code}")


def store_sso_state(state: str, nonce: str) -> None:
    from grc_dashboard.cache import session_store

    session_store.set_json(f"{_SSO_STATE_PREFIX}{state}", {"nonce": nonce}, _SSO_STATE_TTL_SECONDS)


def pop_sso_state(state: str) -> str | None:
    from grc_dashboard.cache import session_store

    payload = session_store.get_json(f"{_SSO_STATE_PREFIX}{state}")
    if not payload:
        return None
    return str(payload.get("nonce", ""))


def map_role_from_claims(
    claims: dict[str, Any],
    default_role: str,
    group_role_map: dict[str, str] | None = None,
) -> str:
    roles = claims.get("roles") or []
    groups = claims.get("groups") or []
    if isinstance(roles, str):
        roles = [roles]
    if isinstance(groups, str):
        groups = [groups]

    normalized = {str(value).lower() for value in [*roles, *groups]}
    for candidate in ("admin", "ciso", "analyst", "auditor"):
        if candidate in normalized:
            return candidate

    if group_role_map:
        for group_name, role in group_role_map.items():
            if group_name in normalized:
                return role

    return default_role


def profile_from_claims(
    claims: dict[str, Any],
    default_role: str,
    group_role_map: dict[str, str] | None = None,
) -> dict[str, str]:
    email = (
        claims.get("email")
        or claims.get("preferred_username")
        or claims.get("upn")
        or ""
    ).lower()
    username = (
        claims.get("preferred_username")
        or claims.get("upn")
        or email.split("@")[0]
        or "sso_user"
    )
    if "@" in username:
        username = username.split("@")[0]

    full_name = claims.get("name") or username.replace(".", " ").title()
    return {
        "username": username[:100],
        "email": email[:255] or f"{username}@sso.local",
        "full_name": full_name[:200],
        "role": map_role_from_claims(claims, default_role, group_role_map),
    }


def provider_setup_guide(provider: str) -> dict[str, Any]:
    """Return operator checklist for the configured provider."""
    guides = {
        "azure": {
            "provider": "Microsoft Entra ID (Azure AD)",
            "portal_url": "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps",
            "required_env": [
                "AUTH_SSO_ENABLED=true",
                "AUTH_SSO_PROVIDER=azure",
                "AUTH_AZURE_TENANT_ID=<your-tenant-guid>",
                "AUTH_OIDC_CLIENT_ID=<app-registration-client-id>",
                "AUTH_OIDC_CLIENT_SECRET=<client-secret-value>",
                "AUTH_OIDC_REDIRECT_URI=https://<your-domain>/api/auth/sso/callback",
            ],
            "app_registration_steps": [
                "Register an app → Web redirect URI: AUTH_OIDC_REDIRECT_URI",
                "Certificates & secrets → New client secret",
                "Token configuration → optional: add app roles admin, ciso, analyst, auditor",
                "Enterprise applications → assign users/groups and app roles",
                "Manifest → ensure idToken has roles claim when using app roles",
            ],
            "role_mapping": (
                "Create Entra app roles named admin, ciso, analyst, or auditor, "
                "or set AUTH_SSO_GROUP_ROLE_MAP=Entra-Admin-Group:admin,Entra-Auditors:auditor"
            ),
        },
        "okta": {
            "provider": "Okta",
            "portal_url": "https://developer.okta.com/docs/guides/implement-auth-code/",
            "required_env": [
                "AUTH_SSO_ENABLED=true",
                "AUTH_SSO_PROVIDER=okta",
                "AUTH_OKTA_DOMAIN=<your-org>.okta.com",
                "AUTH_OKTA_AUTH_SERVER=default",
                "AUTH_OIDC_CLIENT_ID=<okta-client-id>",
                "AUTH_OIDC_CLIENT_SECRET=<okta-client-secret>",
                "AUTH_OIDC_REDIRECT_URI=https://<your-domain>/api/auth/sso/callback",
            ],
            "app_registration_steps": [
                "Applications → Create App Integration → OIDC → Web",
                "Sign-in redirect URI: AUTH_OIDC_REDIRECT_URI",
                "Assign users/groups to the application",
                "Authorization server → add groups claim to ID token if using groups",
            ],
            "role_mapping": (
                "Name Okta groups admin/ciso/analyst/auditor, or map with "
                "AUTH_SSO_GROUP_ROLE_MAP=Okta-Admins:admin,Okta-Auditors:auditor"
            ),
        },
    }
    return guides.get(provider.lower(), {
        "provider": "Generic OIDC",
        "portal_url": None,
        "required_env": [
            "AUTH_SSO_ENABLED=true",
            "AUTH_SSO_PROVIDER=oidc",
            "AUTH_OIDC_ISSUER_URL=https://<idp>/.well-known/openid-configuration (issuer root)",
            "AUTH_OIDC_CLIENT_ID=<client-id>",
            "AUTH_OIDC_CLIENT_SECRET=<client-secret>",
            "AUTH_OIDC_REDIRECT_URI=https://<your-domain>/api/auth/sso/callback",
        ],
        "app_registration_steps": [
            "Register a confidential OIDC client with authorization code flow",
            "Set redirect URI to AUTH_OIDC_REDIRECT_URI",
        ],
        "role_mapping": "Use AUTH_SSO_GROUP_ROLE_MAP or roles/groups claims named admin|ciso|analyst|auditor",
    })
