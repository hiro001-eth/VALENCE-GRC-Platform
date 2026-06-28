"""Production-safe demo sandbox credential management."""
from __future__ import annotations

import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

VALENCE_ENV = os.getenv("VALENCE_ENV", "development").lower()
CREDENTIALS_FILE = Path(os.getenv("VALENCE_DEMO_CREDENTIALS_FILE", "data/demo_credentials.json"))


def seed_demo_users_enabled() -> bool:
    default = "false" if VALENCE_ENV == "production" else "true"
    return os.getenv("VALENCE_SEED_DEMO_USERS", default).lower() in {"1", "true", "yes"}


def show_credential_hints() -> bool:
    if VALENCE_ENV != "production":
        return True
    return os.getenv("VALENCE_SHOW_DEMO_CREDENTIALS", "false").lower() in {"1", "true", "yes"}


def resolve_demo_password(role: str) -> str:
    """Return password for a demo role — env override, file, or dev defaults."""
    unified = os.getenv("VALENCE_DEMO_PASSWORD", "").strip()
    if unified:
        return unified

    if VALENCE_ENV != "production":
        defaults = {
            "admin": "valence123",
            "ciso": "ciso123",
            "analyst": "analyst123",
            "auditor": "auditor123",
        }
        return defaults.get(role, "valence123")

    if CREDENTIALS_FILE.exists():
        try:
            stored = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
            return str(stored.get(role, stored.get("password", "")))
        except Exception:
            pass

    password = secrets.token_urlsafe(16)
    _persist_generated_credentials({role: password})
    return password


def ensure_demo_credential_file() -> dict[str, Any] | None:
    """Generate and persist rotated demo passwords for production pilots."""
    if not seed_demo_users_enabled() or VALENCE_ENV != "production":
        return None
    if os.getenv("VALENCE_DEMO_PASSWORD", "").strip():
        return {"mode": "env", "message": "Using VALENCE_DEMO_PASSWORD for all sandbox accounts"}

    if CREDENTIALS_FILE.exists():
        try:
            return json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    creds = {role: secrets.token_urlsafe(14) for role in ("admin", "ciso", "analyst", "auditor")}
    creds["generated_at"] = datetime.now(UTC).isoformat()
    creds["mode"] = "rotated"
    _persist_generated_credentials(creds)
    logger.warning(
        "demo_credentials_rotated",
        path=str(CREDENTIALS_FILE),
        message="Retrieve sandbox passwords from the credentials file — not logged for security",
    )
    return creds


def _persist_generated_credentials(creds: dict[str, Any]) -> None:
    CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_FILE.write_text(json.dumps(creds, indent=2), encoding="utf-8")
    try:
        CREDENTIALS_FILE.chmod(0o600)
    except OSError:
        pass
