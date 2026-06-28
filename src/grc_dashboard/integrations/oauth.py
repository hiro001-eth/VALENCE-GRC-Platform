"""OAuth 2.0 flows for marketplace integrations."""
from __future__ import annotations

import hashlib
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog

from grc_dashboard.cache import session_store
from grc_dashboard.integrations.marketplace_catalog import OAUTH_PROVIDERS

logger = structlog.get_logger(__name__)

_OAUTH_STATE_TTL = 600


def _base_url() -> str:
    return os.getenv("VALENCE_PUBLIC_URL", "http://localhost:8000").rstrip("/")


def is_oauth_configured(provider: str) -> bool:
    cfg = OAUTH_PROVIDERS.get(provider)
    if not cfg:
        return False
    return bool(os.getenv(cfg["env_client_id"]) and os.getenv(cfg["env_client_secret"]))


def _production_oauth_required() -> bool:
    is_prod = os.getenv("VALENCE_ENV", "development").lower() == "production"
    return is_prod and os.getenv("VALENCE_ALLOW_DEMO_OAUTH", "false").lower() not in {"1", "true", "yes"}


def start_oauth_flow(tenant_id: str, provider: str, username: str, extra: dict[str, str] | None = None) -> dict[str, Any]:
    cfg = OAUTH_PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"OAuth not supported for {provider}")
    client_id = os.getenv(cfg["env_client_id"], "")
    client_secret = os.getenv(cfg["env_client_secret"], "")
    if not client_id or not client_secret:
        if _production_oauth_required():
            raise ValueError(
                f"Live OAuth required in production. Set {cfg['env_client_id']} and {cfg['env_client_secret']}."
            )
        return {
            "mode": "demo",
            "authorize_url": None,
            "message": f"Set {cfg['env_client_id']} and {cfg['env_client_secret']} to enable live OAuth.",
            "demo_connect": True,
        }

    state = secrets.token_urlsafe(24)
    session_store.set_json(
        f"oauth_state:{state}",
        {"tenant_id": tenant_id, "provider": provider, "username": username, "extra": extra or {}},
        _OAUTH_STATE_TTL,
    )
    redirect_uri = f"{_base_url()}/api/integrations/oauth/callback"
    auth_url = cfg["authorize_url"]
    if "{org_url}" in auth_url:
        org = (extra or {}).get("org_url", os.getenv("OKTA_ORG_URL", "https://example.okta.com"))
        auth_url = auth_url.replace("{org_url}", org.rstrip("/"))
    if "{tenant}" in auth_url:
        tid = (extra or {}).get("azure_tenant", os.getenv("AZURE_TENANT_ID", "common"))
        auth_url = auth_url.replace("{tenant}", tid)
    if "{instance_url}" in auth_url:
        inst = (extra or {}).get("instance_url", os.getenv("SERVICENOW_INSTANCE_URL", "https://demo.service-now.com"))
        auth_url = auth_url.replace("{instance_url}", inst.rstrip("/"))

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": cfg["scope"],
        "state": state,
    }
    if provider == "google_workspace":
        params["access_type"] = "offline"
        params["prompt"] = "consent"

    return {"mode": "oauth", "authorize_url": f"{auth_url}?{urlencode(params)}", "state": state}


async def complete_oauth_callback(code: str, state: str) -> dict[str, Any]:
    pending = session_store.get_json(f"oauth_state:{state}")
    if not pending:
        raise ValueError("Invalid or expired OAuth state")

    provider = pending["provider"]
    cfg = OAUTH_PROVIDERS[provider]
    client_id = os.getenv(cfg["env_client_id"], "")
    client_secret = os.getenv(cfg["env_client_secret"], "")
    redirect_uri = f"{_base_url()}/api/integrations/oauth/callback"

    token_url = cfg["token_url"]
    extra = pending.get("extra") or {}
    if "{org_url}" in token_url:
        org = extra.get("org_url", os.getenv("OKTA_ORG_URL", ""))
        token_url = token_url.replace("{org_url}", org.rstrip("/"))
    if "{tenant}" in token_url:
        tid = extra.get("azure_tenant", os.getenv("AZURE_TENANT_ID", "common"))
        token_url = token_url.replace("{tenant}", tid)
    if "{instance_url}" in token_url:
        inst = extra.get("instance_url", os.getenv("SERVICENOW_INSTANCE_URL", "https://demo.service-now.com"))
        token_url = token_url.replace("{instance_url}", inst.rstrip("/"))

    async with httpx.AsyncClient(timeout=20.0) as client:
        if provider == "github":
            res = await client.post(
                token_url,
                headers={"Accept": "application/json"},
                json={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
        else:
            res = await client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
        if res.status_code not in (200, 201):
            logger.warning("oauth_token_failed", provider=provider, status=res.status_code)
            raise ValueError("Token exchange failed")
        tokens = res.json()

    access_token = tokens.get("access_token", "")
    refresh = tokens.get("refresh_token", "")
    return {
        "tenant_id": pending["tenant_id"],
        "provider": provider,
        "configured_by": pending["username"],
        "secrets": {"api_key": access_token, "refresh_token": refresh},
        "metadata": extra,
    }


def demo_oauth_connect(tenant_id: str, provider: str, username: str, extra: dict[str, str] | None = None) -> dict[str, Any]:
    """Demo-mode OAuth when client credentials are not configured."""
    token = hashlib.sha256(f"{tenant_id}:{provider}:{time.time()}".encode()).hexdigest()[:32]
    return {
        "tenant_id": tenant_id,
        "provider": provider,
        "configured_by": username,
        "secrets": {"api_key": f"demo_oauth_{token}"},
        "metadata": extra or {},
        "oauth_mode": "demo",
    }
