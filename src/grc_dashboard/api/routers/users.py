"""Team user management — invite GRC/SOC/IR members with feature-scoped access."""
from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.auth.dependencies import CurrentUser, RequireAdmin, require_feature
from grc_dashboard.auth.features import (
    ALL_FEATURES,
    DEPARTMENT_LABELS,
    DEPARTMENT_PRESETS,
    DEPARTMENTS,
    FEATURE_LABELS,
    allowed_feature_list,
    resolve_features,
)
from grc_dashboard.auth.jwt_handler import hash_password
from grc_dashboard.billing.entitlements import enforce_seat_limit, require_active_subscription
from grc_dashboard.db.models import Tenant, User
from grc_dashboard.db.session import get_db
from grc_dashboard.tenancy.constants import is_demo_username

logger = structlog.get_logger(__name__)
router = APIRouter()


class InviteUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    email: str = Field(min_length=5, max_length=255)
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="analyst", pattern="^(admin|ciso|analyst|auditor)$")
    department: str = Field(default="general")
    features: list[str] | None = None


class UpdateUserRequest(BaseModel):
    full_name: str | None = None
    role: str | None = None
    department: str | None = None
    features: list[str] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


def _user_row(user: User) -> dict[str, Any]:
    features = resolve_features(user.role, user.department, user.feature_permissions)
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "department": user.department,
        "department_label": DEPARTMENT_LABELS.get(user.department, user.department),
        "is_active": user.is_active,
        "features": features,
        "feature_list": [f for f, ok in features.items() if ok],
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


@router.get("/catalog")
async def feature_catalog(current_user: User = CurrentUser) -> dict[str, Any]:
    """Feature and department catalog for the team admin UI."""
    return {
        "features": [{"id": f, "label": FEATURE_LABELS[f]} for f in ALL_FEATURES if f != "team_admin"],
        "departments": [
            {"id": d, "label": DEPARTMENT_LABELS[d], "preset_features": DEPARTMENT_PRESETS.get(d, [])}
            for d in DEPARTMENTS
        ],
        "roles": ["admin", "ciso", "analyst", "auditor"],
    }


@router.get("/me/features")
async def my_features(current_user: User = CurrentUser) -> dict[str, Any]:
    features = resolve_features(
        current_user.role, current_user.department, current_user.feature_permissions
    )
    return {
        "role": current_user.role,
        "department": current_user.department,
        "features": features,
        "feature_list": [f for f, ok in features.items() if ok],
    }


@router.get("/")
async def list_team_members(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(require_feature("team_admin")),
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(User)
        .where(User.tenant_id == current_user.tenant_id)
        .order_by(User.created_at.asc())
    )
    return [_user_row(u) for u in result.scalars().all()]


@router.post("/", status_code=201)
async def invite_team_member(
    body: InviteUserRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(require_feature("team_admin")),
) -> dict[str, Any]:
    if body.department not in DEPARTMENTS:
        raise HTTPException(status_code=400, detail=f"department must be one of: {', '.join(DEPARTMENTS)}")

    username = body.username.strip().lower()
    if is_demo_username(username):
        raise HTTPException(status_code=400, detail="This username is reserved for sandbox accounts")

    for field, value in (("username", username), ("email", body.email.lower())):
        existing = await db.execute(select(User).where(getattr(User, field) == value))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"{field} already registered")

    if body.role == "admin" and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create other admins")

    tenant = await db.get(Tenant, current_user.tenant_id)
    if tenant:
        require_active_subscription(tenant)
        await enforce_seat_limit(db, tenant)

    feature_map = None
    if body.features is not None:
        feature_map = {f: f in body.features for f in ALL_FEATURES}
    elif body.department in DEPARTMENT_PRESETS:
        preset = set(DEPARTMENT_PRESETS[body.department])
        if body.role == "admin":
            preset.add("team_admin")
        feature_map = {f: f in preset for f in ALL_FEATURES}

    user = User(
        tenant_id=current_user.tenant_id,
        username=username,
        email=body.email.lower(),
        hashed_password=hash_password(body.password),
        full_name=body.full_name.strip(),
        role=body.role,
        department=body.department,
        feature_permissions=feature_map,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("team_member_invited", tenant_id=current_user.tenant_id, username=username, department=body.department)
    return _user_row(user)


@router.patch("/{user_id}")
async def update_team_member(
    user_id: int,
    body: UpdateUserRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(require_feature("team_admin")),
) -> dict[str, Any]:
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == current_user.tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id and body.is_active is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    if body.role is not None:
        if body.role == "admin" and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only admins can assign admin role")
        user.role = body.role
    if body.department is not None:
        if body.department not in DEPARTMENTS:
            raise HTTPException(status_code=400, detail="Invalid department")
        user.department = body.department
    if body.features is not None:
        user.feature_permissions = {f: f in body.features for f in ALL_FEATURES}
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password:
        user.hashed_password = hash_password(body.password)

    await db.commit()
    await db.refresh(user)
    return _user_row(user)


@router.delete("/{user_id}", status_code=204)
async def deactivate_team_member(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(require_feature("team_admin")),
) -> None:
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == current_user.tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    await db.commit()
