"""Tenant runtime context — data mode, SIEM status, honest UI labels."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id, get_tenant_results
from grc_dashboard.auth.dependencies import CurrentUser
from grc_dashboard.auth.features import allowed_feature_list, resolve_features
from grc_dashboard.db.models import IntegrationSettings, ReportRecord, Tenant, User
from grc_dashboard.db.session import get_db
from grc_dashboard.tenancy.constants import is_demo_tenant, is_demo_username
from grc_dashboard.tenancy.demo_scenarios import TENANT_PROFILES

router = APIRouter()


@router.get("/context")
async def get_tenant_context(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = CurrentUser,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    tenant = await db.get(Tenant, tenant_id)
    results = get_tenant_results(request)

    settings_row = await db.execute(
        select(IntegrationSettings).where(IntegrationSettings.tenant_id == tenant_id)
    )
    settings = settings_row.scalar_one_or_none()

    is_demo = is_demo_tenant(tenant_id) or is_demo_username(current_user.username)
    siem_type = (settings.siem_type if settings else "") or ""
    siem_configured = siem_type.lower() not in ("", "demo", "none")
    pipeline_status = results.get("pipeline_status", "ok" if is_demo else "pending")
    is_demo_data = is_demo or results.get("is_demo", False)

    if is_demo_data:
        data_mode = "sandbox"
        data_label = "Sandbox scenario data"
        badge = "ACTIVE"
        badge_color = "#16a34a"
        status_line = "Curated evaluation scenario — not your organization's SIEM"
    elif not siem_configured:
        data_mode = "awaiting_siem"
        data_label = "Awaiting SIEM connection"
        badge = "SIEM REQUIRED"
        badge_color = "#d97706"
        status_line = "Connect your SIEM in Infrastructure → SIEM Connectors to load live metrics"
    elif pipeline_status == "failed":
        data_mode = "error"
        data_label = "Pipeline error"
        badge = "PIPELINE ERROR"
        badge_color = "#dc2626"
        status_line = results.get("error", "Metric pipeline failed — check SIEM credentials")
    else:
        data_mode = "live"
        data_label = "Live organizational data"
        badge = "LIVE"
        badge_color = "#16a34a"
        status_line = "SHA-256 audit lineage active — metrics from your connected SIEM"

    profile = TENANT_PROFILES.get(tenant_id, {})
    features = resolve_features(
        current_user.role, current_user.department, current_user.feature_permissions
    )

    onboarded = bool(settings.onboarded) if settings else is_demo
    team_count_result = await db.execute(
        select(User.id).where(User.tenant_id == tenant_id, User.is_active.is_(True))
    )
    team_count = len(team_count_result.all())
    report_count_result = await db.execute(
        select(ReportRecord.id).where(ReportRecord.tenant_id == tenant_id).limit(1)
    )
    has_report = report_count_result.scalar_one_or_none() is not None

    onboarding_step = 1
    if siem_configured:
        onboarding_step = 2
    if team_count > 1:
        onboarding_step = 3
    if has_report:
        onboarding_step = 4

    show_onboarding_wizard = (
        not is_demo_data
        and not is_demo_username(current_user.username)
        and current_user.role == "admin"
        and not onboarded
    )

    return {
        "tenant_id": tenant_id,
        "tenant_name": tenant.name if tenant else profile.get("name", tenant_id),
        "industry": tenant.industry if tenant and tenant.industry else profile.get("industry", ""),
        "is_demo": is_demo_data,
        "is_sandbox_user": is_demo_username(current_user.username),
        "data_mode": data_mode,
        "data_label": data_label,
        "status_badge": badge,
        "status_badge_color": badge_color,
        "status_message": status_line,
        "siem_connected": siem_configured and pipeline_status == "ok",
        "siem_type": siem_type or "not_configured",
        "pipeline_status": pipeline_status,
        "onboarded": onboarded,
        "onboarding_step": onboarding_step,
        "show_onboarding_wizard": show_onboarding_wizard,
        "team_count": team_count,
        "has_report": has_report,
        "features": features,
        "feature_list": allowed_feature_list(
            current_user.role, current_user.department, current_user.feature_permissions
        ),
        "user": {
            "username": current_user.username,
            "role": current_user.role,
            "department": current_user.department,
            "tenant_id": current_user.tenant_id,
            "is_demo_account": is_demo_username(current_user.username),
        },
    }
