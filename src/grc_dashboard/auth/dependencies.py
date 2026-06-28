"""FastAPI dependency injection for auth + RBAC."""
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.auth.features import FEATURE_LABELS, has_feature
from grc_dashboard.auth.jwt_handler import decode_token
from grc_dashboard.db.models import User
from grc_dashboard.db.session import get_db

logger = structlog.get_logger(__name__)

security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)

ROLE_HIERARCHY = {
    "admin": 4,
    "ciso": 3,
    "analyst": 2,
    "auditor": 1,
}


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Extract and validate JWT token; return the authenticated User."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise credentials_exception
        username: str = payload.get("sub", "")
        if not username:
            raise credentials_exception
    except ValueError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception

    return user


async def get_current_user_flexible(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security_optional)] = None,
    token: Annotated[str | None, Query()] = None,
) -> User:
    """Accept JWT from Authorization header or ?token= query (downloads / legacy links)."""
    raw = None
    if credentials and credentials.credentials:
        raw = credentials.credentials
    elif token:
        raw = token
    else:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            raw = auth_header[7:].strip()

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not raw:
        raise credentials_exception
    try:
        payload = decode_token(raw)
        if payload.get("type") != "access":
            raise credentials_exception
        username: str = payload.get("sub", "")
        if not username:
            raise credentials_exception
    except ValueError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_role_flexible(minimum_role: str):
    """Like require_role but accepts Bearer header or ?token= query."""
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user_flexible)],
    ) -> User:
        user_level = ROLE_HIERARCHY.get(current_user.role, 0)
        required_level = ROLE_HIERARCHY.get(minimum_role, 99)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {minimum_role} or above.",
            )
        return current_user

    return role_checker


def require_role(minimum_role: str):
    """Factory: returns a FastAPI dependency that enforces a minimum role level."""
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        user_level = ROLE_HIERARCHY.get(current_user.role, 0)
        required_level = ROLE_HIERARCHY.get(minimum_role, 99)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {minimum_role} or above.",
            )
        return current_user

    return role_checker


# Convenience dependencies
RequireAdmin = Depends(require_role("admin"))
RequireCISO = Depends(require_role("ciso"))
RequireAnalyst = Depends(require_role("analyst"))
RequireAuditor = Depends(require_role("auditor"))
CurrentUser = Depends(get_current_user)


def require_feature(feature: str):
    """Enforce per-user feature flag (demo sandbox accounts bypass)."""
    async def checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        from grc_dashboard.tenancy.constants import is_demo_username

        if is_demo_username(current_user.username):
            return current_user

        if not has_feature(
            current_user.role,
            current_user.department,
            current_user.feature_permissions,
            feature,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your account does not have access to: {FEATURE_LABELS.get(feature, feature)}",
            )
        return current_user

    return checker
