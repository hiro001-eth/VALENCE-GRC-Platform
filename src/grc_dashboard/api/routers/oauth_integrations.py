"""OAuth marketplace integration routes."""
from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import UTC, datetime

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireAdmin
from grc_dashboard.billing.entitlements import enforce_integration_limit
from grc_dashboard.db.models import IntegrationSettings, Tenant, User
from grc_dashboard.db.session import get_db
from grc_dashboard.deployment.production import IS_PRODUCTION
from grc_dashboard.integrations.aws_auth import assume_role_credentials
from grc_dashboard.integrations.marketplace_catalog import OAUTH_PROVIDERS
from grc_dashboard.integrations.oauth import (
    complete_oauth_callback,
    demo_oauth_connect,
    is_oauth_configured,
    start_oauth_flow,
)
from grc_dashboard.integrations.token_refresh import get_valid_access_token

router = APIRouter()


class OAuthStartBody(BaseModel):
    provider: str
    org_url: str | None = None
    azure_tenant: str | None = None


class AwsRoleConnectBody(BaseModel):
    role_arn: str = Field(min_length=20)
    external_id: str = Field(min_length=8)
    region: str = "us-east-1"
    account_id: str | None = None


@router.get("/providers")
async def list_oauth_providers(current_user: User = RequireAdmin) -> list[dict[str, Any]]:
    return [
        {
            "provider": pid,
            "configured": is_oauth_configured(pid),
            "scopes": cfg["scope"],
        }
        for pid, cfg in OAUTH_PROVIDERS.items()
    ]


@router.get("/connections")
async def oauth_connections(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    """List connected OAuth providers with quick liveness probes."""
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(IntegrationSettings).where(IntegrationSettings.tenant_id == tenant_id)
    )
    settings = result.scalar_one_or_none()
    connected = dict(settings.connected_integrations or {}) if settings else {}

    providers: list[dict[str, Any]] = []
    for provider, cfg in OAUTH_PROVIDERS.items():
        conn = connected.get(provider, {})
        status = conn.get("status") == "connected"
        token = ((conn.get("secrets") or {}).get("api_key") or "")
        meta = conn.get("metadata") or {}
        if status and token:
            token = await get_valid_access_token(provider, conn.get("secrets") or {}, meta)
        probe = await _probe_oauth_provider(provider, token, meta) if status and token else {"ok": False, "reason": "not_connected"}
        providers.append(
            {
                "provider": provider,
                "connected": status,
                "configured": is_oauth_configured(provider),
                "auth_method": conn.get("auth_method"),
                "metadata": conn.get("metadata") or {},
                "probe": probe,
            }
        )
    return {"tenant_id": tenant_id, "providers": providers}


@router.post("/start")
async def oauth_start(
    body: OAuthStartBody,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    extra: dict[str, str] = {}
    if body.org_url:
        extra["org_url"] = body.org_url
    if body.azure_tenant:
        extra["azure_tenant"] = body.azure_tenant

    if body.provider not in OAUTH_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported OAuth provider")

    if body.provider == "aws":
        raise HTTPException(
            status_code=400,
            detail="AWS uses cross-account IAM role auth. POST /api/integrations/oauth/aws/role with role_arn and external_id.",
        )

    result = start_oauth_flow(tenant_id, body.provider, current_user.username, extra)
    if result.get("demo_connect"):
        if IS_PRODUCTION:
            raise HTTPException(
                status_code=503,
                detail=result.get("message", "Configure OAuth client credentials for live integration."),
            )
        conn = demo_oauth_connect(tenant_id, body.provider, current_user.username, extra)
        await _store_connection(db, tenant_id, conn)
        return {"status": "connected", "mode": "demo_oauth", "provider": body.provider}
    return result


@router.post("/aws/role")
async def connect_aws_cross_account_role(
    body: AwsRoleConnectBody,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    """Connect AWS via cross-account IAM role (production-grade, no fake OAuth)."""
    tenant_id = get_tenant_id(request)
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    creds = assume_role_credentials(body.role_arn, body.external_id, body.region)
    if not creds:
        raise HTTPException(
            status_code=502,
            detail="Failed to assume IAM role. Verify role ARN, external ID, and VALENCE instance profile.",
        )

    conn = {
        "tenant_id": tenant_id,
        "provider": "aws",
        "configured_by": current_user.username,
        "secrets": creds,
        "metadata": {
            "role_arn": body.role_arn,
            "external_id": body.external_id,
            "region": body.region,
            "account_id": body.account_id,
            "auth_method": "cross_account_role",
        },
        "oauth_mode": "iam_role",
    }
    await _store_connection(db, tenant_id, conn)
    return {
        "status": "connected",
        "mode": "live",
        "provider": "aws",
        "account_id": body.account_id,
        "expires_at": creds.get("expires_at"),
    }


@router.get("/callback")
async def oauth_callback(
    code: str = Query(""),
    state: str = Query(""),
    error: str = Query(""),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if error:
        return RedirectResponse(url=f"/?oauth_error={error}")
    try:
        conn = await complete_oauth_callback(code, state)
        await _store_connection(db, conn["tenant_id"], conn)
        return RedirectResponse(url="/?oauth_success=1")
    except Exception as exc:
        return RedirectResponse(url=f"/?oauth_error={str(exc)[:80]}")


async def _store_connection(db: AsyncSession, tenant_id: str, conn: dict[str, Any]) -> None:
    provider = conn["provider"]
    tenant = await db.get(Tenant, tenant_id)
    result = await db.execute(
        select(IntegrationSettings).where(IntegrationSettings.tenant_id == tenant_id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        settings = IntegrationSettings(tenant_id=tenant_id)
        db.add(settings)

    connected = dict(settings.connected_integrations or {})
    if tenant and not conn.get("oauth_mode", "").startswith("demo"):
        enforce_integration_limit(tenant, len([k for k, v in connected.items() if v.get("status") == "connected"]) + 1)

    connected[provider] = {
        "status": "connected",
        "configured_at": datetime.now(UTC).isoformat(),
        "configured_by": conn.get("configured_by", "oauth"),
        "metadata": conn.get("metadata", {}),
        "secrets": conn.get("secrets", {}),
        "auth_method": conn.get("oauth_mode", "oauth"),
    }
    settings.connected_integrations = connected
    await db.commit()


async def _probe_oauth_provider(provider: str, token: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    if not token:
        return {"ok": False, "reason": "missing_token"}
    if token.startswith("demo_oauth_"):
        return {"ok": True, "reason": "demo_mode", "live": False}

    endpoint_map = {
        "github": "https://api.github.com/user",
        "google_workspace": "https://www.googleapis.com/oauth2/v3/userinfo",
        "google": "https://www.googleapis.com/oauth2/v3/userinfo",
        "okta": None,
        "gitlab": "https://gitlab.com/api/v4/user",
    }
    meta = metadata or {}
    if provider == "okta":
        org = meta.get("org_url", "")
        if org:
            endpoint_map["okta"] = f"{org.rstrip('/')}/oauth2/v1/userinfo"

    endpoint = endpoint_map.get(provider)
    if not endpoint:
        return {"ok": True, "reason": "probe_not_required", "live": True}

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(endpoint, headers={"Authorization": f"Bearer {token}"})
            if 200 <= res.status_code < 300:
                return {"ok": True, "http_status": res.status_code, "live": True}
            return {"ok": False, "http_status": res.status_code, "live": False}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:80], "live": False}
