import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from grc_dashboard.cache.session_store import is_token_revoked

_DEFAULT_JWT_SECRETS = frozenset({
    "valence-grc-enterprise-secret-CHANGE-IN-PRODUCTION-minimum-32-chars",
    "changeme",
    "secret",
    "",
})

_MIN_SECRET_LENGTH = 32


def _validate_jwt_secret(secret: str) -> str:
    """Validate JWT secret meets minimum security requirements.

    SECURITY: Prevents production from running with the placeholder default
    secret, which is publicly visible in the repository.
    """
    is_production = os.getenv("VALENCE_ENV", "development").lower() == "production"
    is_testing = bool(os.getenv("PYTEST_CURRENT_TEST")) or "pytest" in __import__("sys").modules

    if is_testing:
        return secret  # Allow test defaults in test mode

    if secret in _DEFAULT_JWT_SECRETS or "CHANGE-IN-PRODUCTION" in secret:
        if is_production:
            raise SystemExit(
                "FATAL: JWT_SECRET_KEY is set to a known default value. "
                "Generate a unique 32+ character secret: python -c \"import secrets; print(secrets.token_urlsafe(48))\" "
                "and set JWT_SECRET_KEY in your .env file."
            )
        import structlog
        structlog.get_logger(__name__).warning(
            "jwt_secret_insecure",
            message="JWT_SECRET_KEY is a known default — MUST be rotated before production",
        )

    if len(secret) < _MIN_SECRET_LENGTH and is_production:
        raise SystemExit(
            f"FATAL: JWT_SECRET_KEY must be at least {_MIN_SECRET_LENGTH} characters. "
            f"Current length: {len(secret)}"
        )

    return secret


SECRET_KEY = _validate_jwt_secret(
    os.getenv("JWT_SECRET_KEY", "valence-grc-enterprise-secret-CHANGE-IN-PRODUCTION-minimum-32-chars")
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    try:
        return bcrypt.checkpw(pwd_bytes, hashed_bytes)
    except Exception:
        return False


def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')



def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access", "jti": str(uuid.uuid4())})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict[str, Any]) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh", "jti": str(uuid.uuid4())})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def token_claims_for_user(user: Any) -> dict[str, Any]:
    from grc_dashboard.tenancy.constants import is_demo_username

    return {
        "sub": user.username,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "demo_access": is_demo_username(user.username),
    }


def decode_token(token: str, *, check_revoked: bool = True) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if check_revoked and is_token_revoked(payload.get("jti", "")):
            raise ValueError("Token has been revoked")
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid or expired token: {e}") from e
