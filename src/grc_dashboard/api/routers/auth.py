"""Authentication router: login, refresh, logout, me, and SSO."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.auth.demo_credentials import (
    ensure_demo_credential_file,
    show_credential_hints,
)
from grc_dashboard.auth.rate_limit import (
    clear_failed_logins,
    is_account_locked,
    is_ip_rate_limited,
    is_refresh_rate_limited,
    lockout_message,
    record_failed_login,
)
from grc_dashboard.auth.dependencies import CurrentUser
from grc_dashboard.auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    token_claims_for_user,
    verify_password,
)
from grc_dashboard.auth.sso import (
    build_authorization_url,
    discover_oidc,
    exchange_code_for_userinfo,
    is_sso_configured,
    load_sso_config,
    pop_sso_exchange,
    pop_sso_state,
    profile_from_claims,
    provider_setup_guide,
    sso_setup_hint,
    store_sso_exchange,
    store_sso_state,
)
from grc_dashboard.db.models import User
from grc_dashboard.db.session import get_db

logger = structlog.get_logger(__name__)
router = APIRouter()

_sso_states: dict[str, tuple[float, str]] = {}  # legacy fallback unused when Redis/memory store active
_SSO_STATE_TTL_SECONDS = 600


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict[str, Any]


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class SSOExchangeRequest(BaseModel):
    code: str


def _user_payload(user: User) -> dict[str, Any]:
    from grc_dashboard.auth.features import allowed_feature_list
    from grc_dashboard.tenancy.constants import is_demo_tenant, is_demo_username

    return {
        "username": user.username,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "department": user.department,
        "is_demo_account": is_demo_username(user.username),
        "is_demo_tenant": is_demo_tenant(user.tenant_id),
        "feature_list": allowed_feature_list(
            user.role, user.department, user.feature_permissions
        ),
    }


def _issue_tokens(user: User) -> TokenResponse:
    claims = token_claims_for_user(user)
    return TokenResponse(
        access_token=create_access_token(claims),
        refresh_token=create_refresh_token(claims),
        user=_user_payload(user),
    )


async def _touch_last_login(db: AsyncSession, user: User) -> None:
    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(last_login=datetime.now(UTC))
    )
    await db.commit()


async def _get_or_create_sso_user(
    db: AsyncSession,
    profile: dict[str, str],
) -> User:
    import os

    result = await db.execute(select(User).where(User.email == profile["email"]))
    user = result.scalar_one_or_none()
    if user:
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
        user.full_name = profile["full_name"] or user.full_name
        user.email = profile["email"]
        if user.role != "admin":
            user.role = profile["role"]
        await db.commit()
        await db.refresh(user)
        return user

    auto_provision = os.getenv("AUTH_SSO_AUTO_PROVISION", "false").lower() in {"1", "true", "yes"}
    default_tenant = os.getenv("AUTH_SSO_DEFAULT_TENANT", "").strip()
    if not auto_provision:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "SSO account not provisioned. Your VALENCE administrator must invite you "
                "via Team Access before you can sign in with SSO."
            ),
        )

    from grc_dashboard.auth.features import allowed_feature_list

    user = User(
        tenant_id=default_tenant or "default",
        username=profile["username"],
        email=profile["email"],
        hashed_password=hash_password(secrets.token_urlsafe(32)),
        full_name=profile["full_name"],
        role=profile["role"],
        department="general",
        feature_permissions={f: True for f in allowed_feature_list(profile["role"], "general", None)},
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("sso_user_provisioned", username=user.username, role=user.role, tenant_id=user.tenant_id)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    client_ip = request.client.host if request.client else "unknown"
    if is_ip_rate_limited(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait and try again.",
        )
    if is_account_locked(body.username):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=lockout_message(body.username),
        )

    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        remaining = record_failed_login(body.username)
        detail = "Incorrect username or password"
        if remaining == 0:
            detail = lockout_message(body.username)
        elif remaining <= 2:
            detail = f"Incorrect username or password. {remaining} attempt(s) remaining before lockout."
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    clear_failed_logins(body.username)
    await _touch_last_login(db, user)
    logger.info("user_login", username=user.username, role=user.role, method="password")
    return _issue_tokens(user)


@router.post("/refresh")
async def refresh_token_endpoint(
    body: RefreshRequest,
    request: Request,
) -> dict[str, str]:
    client_ip = request.client.host if request.client else "unknown"
    if is_refresh_rate_limited(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many token refresh attempts. Please wait and try again.",
        )
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("Not a refresh token")
        new_access = create_access_token(
            {"sub": payload["sub"], "role": payload.get("role", "analyst"),
             "tenant_id": payload.get("tenant_id", "demo-global-hq"),
             "demo_access": payload.get("demo_access", False)}
        )
        return {"access_token": new_access, "token_type": "bearer"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e


@router.post("/logout")
async def logout(request: Request, body: LogoutRequest | None = None) -> dict[str, str]:
    """Revoke access/refresh tokens server-side (Redis or memory denylist)."""
    import time

    from grc_dashboard.cache.session_store import revoke_token_jti

    tokens: list[str] = []
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        tokens.append(auth_header.split(" ", 1)[1].strip())
    if body and body.refresh_token:
        tokens.append(body.refresh_token)

    for token in tokens:
        try:
            payload = decode_token(token, check_revoked=False)
            jti = payload.get("jti", "")
            exp = payload.get("exp")
            ttl = max(int(exp - time.time()), 60) if exp else 3600
            revoke_token_jti(jti, ttl)
        except ValueError:
            continue

    logger.info("user_logout", revoked_tokens=len(tokens))
    return {"status": "logged_out"}


@router.get("/sandbox-info")
async def sandbox_info() -> dict[str, Any]:
    """Whether login UI may show sandbox credential hints (never returns passwords)."""
    ensure_demo_credential_file()
    return {
        "show_credential_hints": show_credential_hints(),
        "environment": __import__("os").getenv("VALENCE_ENV", "development"),
        "message": (
            "Sandbox accounts use rotated credentials in production. "
            "Contact your operator or see data/demo_credentials.json on the server."
            if not show_credential_hints()
            else "Use the four sandbox roles to explore curated enterprise scenarios."
        ),
    }


@router.get("/me")
async def me(current_user: User = CurrentUser) -> dict[str, Any]:
    return {
        **_user_payload(current_user),
        "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
    }


@router.get("/sso/config")
async def sso_config() -> dict[str, Any]:
    config = load_sso_config()
    configured = is_sso_configured(config)
    return {
        "enabled": configured,
        "provider": config.provider if configured else None,
        "setup_hint": sso_setup_hint(config),
    }


@router.get("/sso/setup")
async def sso_setup() -> dict[str, Any]:
    """Operator checklist for wiring Azure Entra ID, Okta, or generic OIDC."""
    config = load_sso_config()
    guide = provider_setup_guide(config.provider)
    return {
        "configured": is_sso_configured(config),
        "setup_hint": sso_setup_hint(config),
        **guide,
    }


@router.get("/sso/login")
async def sso_login() -> RedirectResponse:
    import time

    config = load_sso_config()
    if not is_sso_configured(config):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO is not configured")

    discovery = await discover_oidc(config)
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    store_sso_state(state, nonce)

    auth_url = build_authorization_url(discovery, config, state=state, nonce=nonce)
    return RedirectResponse(auth_url, status_code=status.HTTP_302_FOUND)


@router.get("/sso/callback")
async def sso_callback(
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RedirectResponse:
    import time

    config = load_sso_config()
    if not is_sso_configured(config):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO is not configured")

    expected_nonce = pop_sso_state(state)
    if not expected_nonce:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired SSO state")

    try:
        discovery = await discover_oidc(config)
        claims = await exchange_code_for_userinfo(
            discovery, config, code, expected_nonce=expected_nonce
        )
        profile = profile_from_claims(claims, config.default_role, config.group_role_map)
        user = await _get_or_create_sso_user(db, profile)
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

        await _touch_last_login(db, user)
        tokens = _issue_tokens(user)
        exchange_code = store_sso_exchange(tokens.model_dump())
        logger.info("user_login", username=user.username, role=user.role, method="sso")
        return RedirectResponse(f"/?sso_code={exchange_code}", status_code=status.HTTP_302_FOUND)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("sso_callback_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSO authentication failed",
        ) from exc


@router.post("/sso/exchange", response_model=TokenResponse)
async def sso_exchange(body: SSOExchangeRequest) -> TokenResponse:
    payload = pop_sso_exchange(body.code)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired SSO exchange code",
        )
    return TokenResponse(**payload)
