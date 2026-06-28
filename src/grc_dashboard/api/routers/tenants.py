"""Tenant listing, demo sandboxes, and self-service organization registration."""
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.routers.tenant_context import get_tenant_context
from grc_dashboard.auth.dependencies import CurrentUser
from grc_dashboard.db.models import User
from grc_dashboard.db.session import get_db
from grc_dashboard.tenancy.demo_scenarios import list_demo_tenants
from grc_dashboard.tenancy.service import list_accessible_tenants, register_organization

logger = structlog.get_logger(__name__)
router = APIRouter()


class RegisterOrganizationRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    admin_username: str = Field(min_length=3, max_length=100)
    admin_email: str = Field(min_length=5, max_length=255)
    admin_password: str = Field(min_length=8, max_length=128)
    admin_full_name: str = Field(min_length=2, max_length=200)


@router.get("/demo")
async def get_demo_tenants() -> list[dict[str, str]]:
    """Public catalog of curated sandbox organizations for evaluation."""
    return list_demo_tenants()


@router.get("/accessible")
async def get_accessible_tenants(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = CurrentUser,
) -> list[dict[str, str]]:
    """Tenants the signed-in user may access (home org + demo sandboxes for demo accounts)."""
    return await list_accessible_tenants(db, current_user)


@router.get("/context")
async def tenant_context(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = CurrentUser,
) -> dict[str, Any]:
    """Honest data-mode labels for the UI (sandbox vs live SIEM)."""
    return await get_tenant_context(request, db, current_user)


@router.post("/register", status_code=201)
async def create_organization(
    body: RegisterOrganizationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Self-service: create a company workspace and its first admin user."""
    return await register_organization(
        db,
        company_name=body.company_name,
        admin_username=body.admin_username,
        admin_email=body.admin_email,
        admin_password=body.admin_password,
        admin_full_name=body.admin_full_name,
    )
