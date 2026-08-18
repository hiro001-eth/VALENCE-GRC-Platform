"""OAuth token refresh for live marketplace integrations."""
from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

from grc_dashboard.integrations.marketplace_catalog import OAUTH_PROVIDERS

logger = structlog.get_logger(__name__)


async def refresh_oauth_token(provider: str, secrets: dict[str, Any], metadata: dict[str, Any] | None = None) -> dict[str, str] | None:
    """Refresh an expired OAuth access token. Returns updated secrets or None."""
    refresh = secrets.get("refresh_token", "")
    if not refresh:
        return None

    cfg = OAUTH_PROVIDERS.get(provider)
    if not cfg:
        return None

    client_id = os.getenv(cfg["env_client_id"], "")
    client_secret = os.getenv(cfg["env_client_secret"], "")
    if not client_id or not client_secret:
        return None

    token_url = cfg["token_url"]
    extra = metadata or {}
    if "{org_url}" in token_url:
        org = extra.get("org_url", os.getenv("OKTA_ORG_URL", ""))
        token_url = token_url.replace("{org_url}", org.rstrip("/"))
    if "{tenant}" in token_url:
        tid = extra.get("azure_tenant", os.getenv("AZURE_TENANT_ID", "common"))
        token_url = token_url.replace("{tenant}", tid)
    if "{instance_url}" in token_url:
        inst = extra.get("instance_url", os.getenv("SERVICENOW_INSTANCE_URL", ""))
        token_url = token_url.replace("{instance_url}", inst.rstrip("/"))

    payload: dict[str, str] = {
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            if provider == "github":
                res = await client.post(
                    token_url,
                    headers={"Accept": "application/json"},
                    data=payload,
                )
            else:
                res = await client.post(token_url, data=payload)
            if res.status_code not in (200, 201):
                logger.warning("oauth_refresh_failed", provider=provider, status=res.status_code)
                return None
            tokens = res.json()
    except Exception as exc:
        logger.warning("oauth_refresh_error", provider=provider, error=str(exc))
        return None

    updated = dict(secrets)
    if tokens.get("access_token"):
        updated["api_key"] = tokens["access_token"]
    if tokens.get("refresh_token"):
        updated["refresh_token"] = tokens["refresh_token"]
    return updated


async def get_valid_access_token(
    provider: str,
    secrets: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> str:
    """Return a usable access token, refreshing if a refresh_token is present."""
    token = secrets.get("api_key") or secrets.get("access_token") or ""
    if token.startswith("demo_oauth_"):
        return token
    refreshed = await refresh_oauth_token(provider, secrets, metadata)
    if refreshed:
        return refreshed.get("api_key", token)
    return token
