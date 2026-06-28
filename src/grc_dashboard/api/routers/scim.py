"""SCIM 2.0 user provisioning for enterprise IdP sync (Okta/Azure AD)."""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.auth.jwt_handler import hash_password
from grc_dashboard.billing.entitlements import enforce_seat_limit, require_active_subscription
from grc_dashboard.db.models import Tenant, User
from grc_dashboard.db.session import get_db

router = APIRouter()


class ScimName(BaseModel):
    givenName: str = ""
    familyName: str = ""
    formatted: str = ""


class ScimEmail(BaseModel):
    value: str
    primary: bool = True


class ScimUserCreate(BaseModel):
    userName: str
    name: ScimName | None = None
    emails: list[ScimEmail] = Field(default_factory=list)
    active: bool = True
    externalId: str | None = None


class ScimUserPatch(BaseModel):
    Operations: list[dict[str, Any]]


def _scim_token() -> str:
    return os.getenv("SCIM_BEARER_TOKEN", "").strip()


def _tenant_from_scim(request: Request) -> str:
    return (
        request.headers.get("X-VALENCE-Tenant-ID")
        or os.getenv("SCIM_DEFAULT_TENANT_ID", "")
    ).strip()


async def verify_scim_auth(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    token = _scim_token()
    if not token:
        raise HTTPException(status_code=503, detail="SCIM not configured. Set SCIM_BEARER_TOKEN.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing SCIM bearer token")
    if not secrets.compare_digest(authorization[7:], token):
        raise HTTPException(status_code=401, detail="Invalid SCIM bearer token")
    tenant_id = _tenant_from_scim(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Set X-VALENCE-Tenant-ID header or SCIM_DEFAULT_TENANT_ID")
    return tenant_id


def _scim_user(user: User) -> dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": str(user.id),
        "userName": user.username,
        "name": {"formatted": user.full_name},
        "emails": [{"value": user.email, "primary": True}],
        "active": user.is_active,
        "meta": {
            "resourceType": "User",
            "created": user.created_at.isoformat() if user.created_at else None,
            "lastModified": datetime.now(UTC).isoformat(),
        },
    }


@router.get("/ServiceProviderConfig")
async def service_provider_config() -> dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "patch": {"supported": True},
        "bulk": {"supported": False},
        "filter": {"supported": True, "maxResults": 200},
        "authenticationSchemes": [
            {
                "type": "oauthbearertoken",
                "name": "Bearer Token",
                "primary": True,
            }
        ],
    }


@router.get("/Users")
async def list_users(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[str, Depends(verify_scim_auth)],
    filter: str | None = Query(default=None),
    startIndex: int = Query(default=1, ge=1),
    count: int = Query(default=100, ge=1, le=200),
) -> dict[str, Any]:
    query = select(User).where(User.tenant_id == tenant_id)
    if filter and "userName eq" in filter:
        username = filter.split('"')[1] if '"' in filter else filter.split()[-1]
        query = query.where(User.username == username)
    result = await db.execute(query)
    users = result.scalars().all()
    resources = [_scim_user(u) for u in users[startIndex - 1 : startIndex - 1 + count]]
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": len(users),
        "startIndex": startIndex,
        "itemsPerPage": len(resources),
        "Resources": resources,
    }


@router.post("/Users", status_code=201)
async def create_user(
    body: ScimUserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[str, Depends(verify_scim_auth)],
) -> dict[str, Any]:
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    require_active_subscription(tenant)
    await enforce_seat_limit(db, tenant)

    existing = await db.execute(select(User).where(User.username == body.userName))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User already exists")

    email = body.emails[0].value if body.emails else f"{body.userName}@scim.local"
    full_name = (body.name.formatted if body.name else "") or body.userName
    temp_password = secrets.token_urlsafe(24)

    user = User(
        tenant_id=tenant_id,
        username=body.userName,
        email=email,
        hashed_password=hash_password(temp_password),
        full_name=full_name,
        role="analyst",
        department="general",
        is_active=body.active,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _scim_user(user)


@router.get("/Users/{user_id}")
async def get_user(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[str, Depends(verify_scim_auth)],
) -> dict[str, Any]:
    user = await db.get(User, user_id)
    if not user or user.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="User not found")
    return _scim_user(user)


@router.patch("/Users/{user_id}")
async def patch_user(
    user_id: int,
    body: ScimUserPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[str, Depends(verify_scim_auth)],
) -> dict[str, Any]:
    user = await db.get(User, user_id)
    if not user or user.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="User not found")

    for op in body.Operations:
        path = op.get("path", "")
        value = op.get("value")
        if path == "active" or (isinstance(value, dict) and "active" in value):
            user.is_active = bool(value.get("active") if isinstance(value, dict) else value)
        if path == "name.formatted" or (isinstance(value, dict) and "formatted" in (value.get("name") or {})):
            if isinstance(value, dict) and "name" in value:
                user.full_name = value["name"].get("formatted", user.full_name)
            else:
                user.full_name = str(value)

    await db.commit()
    await db.refresh(user)
    return _scim_user(user)


@router.delete("/Users/{user_id}", status_code=204, response_class=Response)
async def deactivate_user(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[str, Depends(verify_scim_auth)],
) -> Response:
    user = await db.get(User, user_id)
    if not user or user.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    await db.commit()
    return Response(status_code=204)
