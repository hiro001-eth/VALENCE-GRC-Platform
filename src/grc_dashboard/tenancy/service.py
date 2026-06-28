"""Tenant resolution, access control, and self-service provisioning."""
from __future__ import annotations

import re
import secrets
from typing import Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.auth.jwt_handler import hash_password
from grc_dashboard.auth.features import allowed_feature_list
from grc_dashboard.db.models import Tenant, User
from grc_dashboard.tenancy.constants import (
    DEMO_TENANT_IDS,
    DEMO_USERNAMES,
    is_demo_tenant,
    is_demo_username,
    normalize_tenant_id,
)
from grc_dashboard.tenancy.demo_scenarios import TENANT_PROFILES, list_demo_tenants

logger = structlog.get_logger(__name__)


def slugify_company(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    slug = slug[:40] or "org"
    if slug.startswith("demo-"):
        slug = f"org-{slug}"
    return slug


def resolve_tenant_for_request(
    *,
    jwt_tenant_id: str | None,
    jwt_username: str | None,
    requested_tenant_id: str | None,
) -> str:
    """Bind X-Tenant-ID to the authenticated user; demo users may switch demo tenants."""
    home_tenant = normalize_tenant_id(jwt_tenant_id or "demo-global-hq")
    requested = normalize_tenant_id(requested_tenant_id) if requested_tenant_id else home_tenant

    if requested == home_tenant:
        return home_tenant

    if jwt_username and is_demo_username(jwt_username) and is_demo_tenant(requested):
        return requested

    if not jwt_username:
        if is_demo_tenant(requested):
            return requested
        return home_tenant

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this organization.",
    )


async def ensure_demo_tenants(session: AsyncSession) -> None:
    for tenant_id in DEMO_TENANT_IDS:
        profile = TENANT_PROFILES[tenant_id]
        existing = await session.get(Tenant, tenant_id)
        if existing:
            continue
        session.add(
            Tenant(
                id=tenant_id,
                name=profile["name"],
                industry=profile["industry"],
                region=profile["region"],
                is_demo=True,
                description=profile["description"],
            )
        )
    await session.commit()


async def register_organization(
    session: AsyncSession,
    *,
    company_name: str,
    admin_username: str,
    admin_email: str,
    admin_password: str,
    admin_full_name: str,
) -> dict[str, Any]:
    base_slug = slugify_company(company_name)
    tenant_id = base_slug
    suffix = 0
    while await session.get(Tenant, tenant_id):
        suffix += 1
        tenant_id = f"{base_slug}-{suffix}"

    username = admin_username.strip().lower()
    if is_demo_username(username):
        raise HTTPException(status_code=400, detail="This username is reserved for demo accounts")

    for field, value in (("username", username), ("email", admin_email.lower())):
        result = await session.execute(
            select(User).where(getattr(User, field) == value)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"{field} already registered")

    tenant = Tenant(
        id=tenant_id,
        name=company_name.strip(),
        industry="",
        region="",
        is_demo=False,
        description=f"Organization workspace for {company_name.strip()}",
    )
    user = User(
        tenant_id=tenant_id,
        username=username,
        email=admin_email.lower(),
        hashed_password=hash_password(admin_password),
        full_name=admin_full_name.strip(),
        role="admin",
        department="general",
        feature_permissions={f: True for f in allowed_feature_list("admin", "general", None)},
    )
    session.add(tenant)
    session.add(user)

    from grc_dashboard.db.models import IntegrationSettings

    session.add(
        IntegrationSettings(
            tenant_id=tenant_id,
            siem_type="",
            onboarded=False,
        )
    )
    await session.commit()
    await session.refresh(user)
    logger.info("organization_registered", tenant_id=tenant_id, admin=username)
    return {"tenant_id": tenant_id, "tenant_name": tenant.name, "admin_username": username}


async def list_accessible_tenants(session: AsyncSession, user: User) -> list[dict[str, str]]:
    if is_demo_username(user.username):
        return list_demo_tenants()
    tenant = await session.get(Tenant, user.tenant_id)
    if not tenant:
        return [{"tenant_id": user.tenant_id, "name": user.tenant_id, "is_demo": "false"}]
    return [{
        "tenant_id": tenant.id,
        "name": tenant.name,
        "industry": tenant.industry,
        "is_demo": str(tenant.is_demo).lower(),
    }]
