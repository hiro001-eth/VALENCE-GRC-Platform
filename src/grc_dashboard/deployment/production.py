"""Production startup validation and readiness reporting."""
from __future__ import annotations

import os
import sys
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

VALENCE_ENV = os.getenv("VALENCE_ENV", "development").lower()
IS_PRODUCTION = VALENCE_ENV == "production"
IS_TESTING = (
    os.getenv("VALENCE_ENV", "").lower() in {"test", "testing"}
    or "pytest" in sys.modules
    or bool(os.getenv("PYTEST_CURRENT_TEST"))
)

DEFAULT_JWT_SECRETS = frozenset(
    {
        "valence-grc-enterprise-secret-CHANGE-IN-PRODUCTION-minimum-32-chars",
        "changeme",
        "secret",
    }
)

LOCALHOST_ORIGIN_MARKERS = ("localhost", "127.0.0.1", "0.0.0.0")
PLACEHOLDER_MARKERS = ("change_me", "yourcompany", "example.com")


def _jwt_secret() -> str:
    return os.getenv(
        "JWT_SECRET_KEY",
        "valence-grc-enterprise-secret-CHANGE-IN-PRODUCTION-minimum-32-chars",
    ).strip()


def _database_url() -> str:
    from grc_dashboard.config import resolve_database_url
    return resolve_database_url()


def _redis_url() -> str:
    return os.getenv("REDIS_URL", "").strip()


def _cors_origins() -> list[str]:
    raw = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:8080,http://127.0.0.1:3000,https://localhost",
    )
    return [o.strip() for o in raw.split(",") if o.strip()]


def _smtp_configured() -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    return bool(host and host != "smtp.example.com" and user and "example.com" not in user)


def _show_demo_credentials() -> bool:
    if not IS_PRODUCTION:
        return True
    return os.getenv("VALENCE_SHOW_DEMO_CREDENTIALS", "false").lower() in {"1", "true", "yes"}


def _is_default_jwt(secret: str) -> bool:
    if len(secret) < 32:
        return True
    return secret in DEFAULT_JWT_SECRETS or "CHANGE-IN-PRODUCTION" in secret


def _cors_allows_only_localhost(origins: list[str]) -> bool:
    if not origins:
        return True
    return all(any(marker in o.lower() for marker in LOCALHOST_ORIGIN_MARKERS) for o in origins)


def _contains_placeholder(value: str) -> bool:
    lower = value.lower()
    return any(marker in lower for marker in PLACEHOLDER_MARKERS)


def _cors_has_only_https(origins: list[str]) -> bool:
    return bool(origins) and all(o.lower().startswith("https://") for o in origins)


def collect_readiness() -> dict[str, Any]:
    """Non-fatal readiness report for operators and /api/health/readiness."""
    origins = _cors_origins()
    db_url = _database_url()
    jwt = _jwt_secret()
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, severity: str, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "severity": severity, "detail": detail})

    add(
        "jwt_secret_rotated",
        not _is_default_jwt(jwt),
        "critical",
        "Set JWT_SECRET_KEY to a unique 32+ character secret",
    )
    add(
        "postgres_database",
        db_url.startswith("postgresql+asyncpg://") and not _contains_placeholder(db_url),
        "critical" if IS_PRODUCTION else "info",
        "Production requires DATABASE_URL=postgresql+asyncpg://...",
    )
    add(
        "redis_configured",
        _redis_url().startswith("redis://") and not _contains_placeholder(_redis_url()),
        "critical" if IS_PRODUCTION else "info",
        "Set REDIS_URL for SSO exchange, rate limits, and HA replicas",
    )
    add(
        "cors_restricted",
        bool(origins)
        and _cors_has_only_https(origins)
        and (not IS_PRODUCTION or not _cors_allows_only_localhost(origins)),
        "critical" if IS_PRODUCTION else "info",
        "Set CORS_ALLOWED_ORIGINS to HTTPS app domain(s), no localhost",
    )
    add(
        "demo_credentials_hidden",
        not _show_demo_credentials(),
        "critical" if IS_PRODUCTION else "info",
        "VALENCE_SHOW_DEMO_CREDENTIALS must be false in production",
    )
    add(
        "smtp_configured",
        _smtp_configured(),
        "warning",
        "Configure SMTP_HOST/SMTP_USER for scheduled auditor report delivery",
    )
    public_url = os.getenv("VALENCE_PUBLIC_URL", "").strip()
    add(
        "public_url_configured",
        bool(public_url) and public_url.startswith("https://") and not _contains_placeholder(public_url),
        "critical" if IS_PRODUCTION else "info",
        "Set VALENCE_PUBLIC_URL to your HTTPS public app URL",
    )
    add(
        "hsts_enabled",
        os.getenv("VALENCE_FORCE_HSTS", "false").lower() in {"1", "true", "yes"},
        "warning",
        "Set VALENCE_FORCE_HSTS=true behind TLS termination",
    )
    add(
        "stripe_billing",
        bool(os.getenv("STRIPE_SECRET_KEY", "").strip()) and bool(os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()),
        "warning" if IS_PRODUCTION else "info",
        "Set STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET for live billing",
    )
    add(
        "scim_provisioning",
        bool(os.getenv("SCIM_BEARER_TOKEN", "").strip()),
        "info",
        "Set SCIM_BEARER_TOKEN for enterprise IdP user provisioning",
    )
    add(
        "oauth_integrations",
        any(os.getenv(k, "").strip() for k in (
            "GITHUB_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_ID",
            "OKTA_OAUTH_CLIENT_ID", "AZURE_OAUTH_CLIENT_ID",
        )),
        "warning" if IS_PRODUCTION else "info",
        "Configure OAuth client credentials for live marketplace integrations",
    )
    pen_test = os.getenv("VALENCE_PEN_TEST_ATTESTED", "false").lower() in {"1", "true", "yes"}
    add(
        "penetration_test",
        pen_test,
        "warning",
        "Set VALENCE_PEN_TEST_ATTESTED=true after external pen test (see docs/compliance/)",
    )

    critical_fail = [c for c in checks if not c["ok"] and c["severity"] == "critical"]
    warnings = [c for c in checks if not c["ok"] and c["severity"] == "warning"]

    return {
        "environment": VALENCE_ENV,
        "production_ready": len(critical_fail) == 0,
        "checks": checks,
        "critical_failures": [c["name"] for c in critical_fail],
        "warnings": [c["name"] for c in warnings],
    }


def validate_production_startup() -> None:
    """Fail fast when production env is misconfigured. Skipped during pytest."""
    if IS_TESTING or not IS_PRODUCTION:
        return

    report = collect_readiness()
    failures = report["critical_failures"]
    if failures:
        for check in report["checks"]:
            if check["name"] in failures:
                logger.error("production_config_invalid", check=check["name"], detail=check["detail"])
        msg = (
            "Production startup blocked. Fix critical configuration: "
            + ", ".join(failures)
            + ". See .env.production.example and scripts/validate_production.sh"
        )
        print(msg, file=sys.stderr)
        raise SystemExit(1)

    for check in report["checks"]:
        if not check["ok"] and check["severity"] == "warning":
            logger.warning("production_config_warning", check=check["name"], detail=check["detail"])

    logger.info("production_config_validated", warnings=report["warnings"])
