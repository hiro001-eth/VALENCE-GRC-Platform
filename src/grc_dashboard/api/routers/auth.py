"""Authentication router: login, refresh, logout, me, and SSO."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.auth.demo_credentials import (
    ensure_demo_credential_file,
    show_credential_hints,
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
from grc_dashboard.auth.rate_limit import (
    clear_failed_logins,
    is_account_locked,
    is_ip_rate_limited,
    is_refresh_rate_limited,
    lockout_message,
    record_failed_login,
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
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Issue new access token from refresh token.

    SECURITY: Validates the user still exists and is active in DB on each
    refresh to prevent stale/revoked users from obtaining new tokens.
    """
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

        username = payload.get("sub", "")
        if not username:
            raise ValueError("Token missing subject claim")

        # SECURITY: Verify user still exists and is active in the database
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise ValueError("User account is deactivated or does not exist")

        new_access = create_access_token(
            {"sub": user.username, "role": user.role,
             "tenant_id": user.tenant_id,
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


class AuditorLinkCreate(BaseModel):
    auditor_name: str
    duration_hours: int
    allowed_frameworks: list[str]
    role: str = "auditor"

# --- Auditor link helpers (session-store-backed for persistence + TTL) ---

def _auditor_link_key(token: str) -> str:
    return f"valence:auditor_link:{token}"


def _auditor_links_index_key(tenant_id: str) -> str:
    return f"valence:auditor_links_idx:{tenant_id}"


def _store_auditor_link(token: str, info: dict[str, Any], tenant_id: str, ttl_seconds: int) -> None:
    """Persist auditor link to session store with TTL (Redis or memory-backed)."""
    from grc_dashboard.cache import session_store
    session_store.set_json(_auditor_link_key(token), {**info, "tenant_id": tenant_id}, ttl_seconds)


def _get_auditor_link(token: str) -> dict[str, Any] | None:
    """Retrieve auditor link without consuming it."""
    from grc_dashboard.cache import session_store
    key = _auditor_link_key(token)
    client = session_store._get_redis()  # noqa: SLF001
    if client:
        raw = client.get(key)
        if raw:
            import json
            return json.loads(raw)
        return None
    entry = session_store._memory.get(key)
    if not entry:
        return None
    import time
    body, exp = entry
    if time.time() > exp:
        session_store._memory.pop(key, None)
        return None
    import json
    return json.loads(body)


def _delete_auditor_link(token: str) -> None:
    from grc_dashboard.cache import session_store
    key = _auditor_link_key(token)
    client = session_store._get_redis()  # noqa: SLF001
    if client:
        client.delete(key)
    else:
        session_store._memory.pop(key, None)


AUDITOR_LINKS: dict[str, dict[str, Any]] = {}  # Legacy compat — unused, kept for import safety

@router.post("/auditor-links")
async def create_auditor_link(
    body: AuditorLinkCreate,
    current_user: User = CurrentUser
) -> dict[str, Any]:
    from datetime import timedelta
    if current_user.role not in ("admin", "ciso"):
        raise HTTPException(status_code=403, detail="Only admins or CISOs can provision auditor access links")
    
    token = secrets.token_hex(20)
    expires_at = datetime.now(UTC) + timedelta(hours=body.duration_hours)
    ttl_seconds = max(1, int(body.duration_hours * 3600))
    
    link_info = {
        "token": token,
        "auditor_name": body.auditor_name,
        "expires_at": expires_at.isoformat(),
        "allowed_frameworks": body.allowed_frameworks,
        "role": body.role,
        "created_at": datetime.now(UTC).isoformat(),
        "tenant_id": current_user.tenant_id,
    }
    
    _store_auditor_link(token, link_info, current_user.tenant_id, ttl_seconds)
    return link_info

@router.get("/auditor-links")
async def list_auditor_links(
    current_user: User = CurrentUser
) -> list[dict[str, Any]]:
    """List active auditor links. Uses session store scan (tenant-isolated)."""
    if current_user.role not in ("admin", "ciso"):
        raise HTTPException(status_code=403, detail="Access denied")
    # NOTE: In production with Redis, a proper index key or scan should be used.
    # For the memory fallback, iterate the memory store.
    import json as _json
    import time as _time

    from grc_dashboard.cache import session_store

    prefix = "valence:auditor_link:"
    active_links: list[dict[str, Any]] = []
    client = session_store._get_redis()  # noqa: SLF001
    if client:
        for key in client.scan_iter(f"{prefix}*"):
            raw = client.get(key)
            if raw:
                info = _json.loads(raw)
                if info.get("tenant_id") == current_user.tenant_id:
                    active_links.append(info)
    else:
        now = _time.time()
        for key, (body, exp) in list(session_store._memory.items()):
            if key.startswith(prefix) and exp > now:
                info = _json.loads(body)
                if info.get("tenant_id") == current_user.tenant_id:
                    active_links.append(info)
    return active_links

@router.post("/auditor-links/{token}/revoke")
async def revoke_auditor_link(
    token: str,
    current_user: User = CurrentUser
) -> dict[str, str]:
    if current_user.role not in ("admin", "ciso"):
        raise HTTPException(status_code=403, detail="Access denied")
    
    info = _get_auditor_link(token)
    if not info:
        raise HTTPException(status_code=404, detail="Token not found")
    # Tenant isolation: only revoke links belonging to your tenant
    if info.get("tenant_id") != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Token not found")
    _delete_auditor_link(token)
    return {"status": "revoked"}

class TokenLoginRequest(BaseModel):
    token: str

@router.post("/auditor-token-login")
async def auditor_token_login(
    body: TokenLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TokenResponse:
    from datetime import timedelta
    now = datetime.now(UTC)
    info = _get_auditor_link(body.token)
    if not info:
        raise HTTPException(status_code=401, detail="Invalid or expired Auditor Access Link")
    
    exp = datetime.fromisoformat(info["expires_at"])
    if now >= exp:
        _delete_auditor_link(body.token)
        raise HTTPException(status_code=401, detail="Auditor Access Link has expired")
        
    result = await db.execute(select(User).where(User.username == "auditor"))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=500, detail="Default Auditor profile not found on server")
    
    claims = token_claims_for_user(user)
    claims["allowed_frameworks"] = info["allowed_frameworks"]
    claims["auditor_name"] = info["auditor_name"]
    
    seconds_left = max(1, int((exp - now).total_seconds()))
    access_token = create_access_token(claims, expires_delta=timedelta(seconds=seconds_left))
    
    user_payload = _user_payload(user)
    user_payload["username"] = f"{info['auditor_name']} (Temporary)"
    user_payload["full_name"] = info["auditor_name"]
    user_payload["role"] = "auditor"
    
    logger.info("auditor_temp_token_login", auditor=info["auditor_name"], expires_at=info["expires_at"])
    
    return TokenResponse(
        access_token=access_token,
        refresh_token="",
        user=user_payload
    )
