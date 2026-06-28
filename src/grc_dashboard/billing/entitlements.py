"""Plan entitlements and subscription enforcement."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.db.models import Tenant, User
from grc_dashboard.deployment.production import IS_PRODUCTION

PLAN_LIMITS: dict[str, dict[str, int]] = {
    "trial": {"seats": 5, "frameworks": 1, "integrations": 3},
    "starter": {"seats": 10, "frameworks": 2, "integrations": 10},
    "growth": {"seats": 50, "frameworks": 5, "integrations": 25},
    "enterprise": {"seats": 500, "frameworks": 99, "integrations": 99},
}

ACTIVE_STATUSES = frozenset({"active", "active_demo", "trialing"})


def plan_limits(plan: str) -> dict[str, int]:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["trial"])


def subscription_allows_access(tenant: Tenant) -> bool:
    if tenant.is_demo:
        return True
    status = (tenant.subscription_status or "trialing").lower()
    if status in ACTIVE_STATUSES:
        if status == "trialing" and tenant.trial_ends_at:
            return tenant.trial_ends_at.replace(tzinfo=UTC) > datetime.now(UTC)
        return True
    return status not in {"cancelled", "past_due", "unpaid"}


async def enforce_seat_limit(db: AsyncSession, tenant: Tenant) -> None:
    limits = plan_limits(tenant.plan or "trial")
    result = await db.execute(
        select(func.count()).select_from(User).where(
            User.tenant_id == tenant.id,
            User.is_active.is_(True),
        )
    )
    count = int(result.scalar() or 0)
    if count >= limits["seats"]:
        raise HTTPException(
            status_code=402,
            detail=f"Seat limit reached ({limits['seats']}) for plan '{tenant.plan}'. Upgrade to add users.",
        )


def enforce_framework_limit(tenant: Tenant, selected_count: int) -> None:
    limits = plan_limits(tenant.plan or "trial")
    if selected_count > limits["frameworks"]:
        raise HTTPException(
            status_code=402,
            detail=f"Framework limit ({limits['frameworks']}) exceeded for plan '{tenant.plan}'.",
        )


def enforce_integration_limit(tenant: Tenant, connected_count: int) -> None:
    limits = plan_limits(tenant.plan or "trial")
    if connected_count > limits["integrations"]:
        raise HTTPException(
            status_code=402,
            detail=f"Integration limit ({limits['integrations']}) exceeded for plan '{tenant.plan}'.",
        )


def require_active_subscription(tenant: Tenant) -> None:
    if tenant.is_demo:
        return
    if not subscription_allows_access(tenant):
        raise HTTPException(
            status_code=402,
            detail="Subscription inactive or trial expired. Update billing to continue.",
        )


def stripe_required_for_checkout() -> bool:
    """In production, Stripe must be configured — no silent demo upgrades."""
    if not IS_PRODUCTION:
        return False
    return not bool(os.getenv("STRIPE_SECRET_KEY", "").strip())


def entitlements_summary(tenant: Tenant, seat_count: int, integration_count: int) -> dict[str, Any]:
    limits = plan_limits(tenant.plan or "trial")
    return {
        "plan": tenant.plan,
        "subscription_status": tenant.subscription_status,
        "limits": limits,
        "usage": {"seats": seat_count, "integrations": integration_count},
        "access_allowed": subscription_allows_access(tenant),
    }
