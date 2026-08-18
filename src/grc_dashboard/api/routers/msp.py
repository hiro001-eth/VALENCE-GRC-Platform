"""MSP / consultant multi-tenant console."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.auth.dependencies import RequireAdmin
from grc_dashboard.db.models import IntegrationSettings, Tenant, User
from grc_dashboard.db.session import get_db
from grc_dashboard.tenancy.constants import is_demo_username
from grc_dashboard.tenancy.service import list_accessible_tenants

router = APIRouter()


@router.get("/portfolio")
async def msp_portfolio(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    """Cross-tenant portfolio view for MSP admins and demo operators."""
    if not is_demo_username(current_user.username) and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="MSP console requires admin or operator access")

    tenants = await list_accessible_tenants(db, current_user)
    portfolio = []
    for t in tenants:
        tid = t["tenant_id"]
        settings_res = await db.execute(
            select(IntegrationSettings).where(IntegrationSettings.tenant_id == tid)
        )
        settings = settings_res.scalar_one_or_none()
        connected = len([
            1 for v in (settings.connected_integrations or {}).values()
            if v.get("status") == "connected"
        ]) if settings else 0
        tenant_row = await db.get(Tenant, tid)
        portfolio.append({
            "tenant_id": tid,
            "name": t.get("name", tid),
            "plan": tenant_row.plan if tenant_row else "trial",
            "subscription_status": tenant_row.subscription_status if tenant_row else "unknown",
            "connected_integrations": connected,
            "siem_configured": bool(settings and settings.siem_type),
            "is_demo": t.get("is_demo") == "true",
        })

    return {
        "portfolio": portfolio,
        "total_tenants": len(portfolio),
        "note": "MSP console for consultants managing multiple VALENCE organizations.",
    }
