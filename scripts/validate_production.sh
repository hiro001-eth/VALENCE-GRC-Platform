#!/usr/bin/env bash
# Validate production configuration before deploy.
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${1:-.env}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — copy .env.production.example to .env first."
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

fail() { echo "FAIL: $1"; ERRORS=$((ERRORS + 1)); }
warn() { echo "WARN: $1"; WARNINGS=$((WARNINGS + 1)); }
ok()   { echo "OK:   $1"; }

contains_placeholder() {
  local val="${1:-}"
  local upper
  upper="$(printf "%s" "$val" | tr '[:lower:]' '[:upper:]')"
  [[ -z "$val" || "$upper" == *"CHANGE_ME"* || "$upper" == *"YOURCOMPANY"* || "$upper" == *"EXAMPLE.COM"* ]]
}

ERRORS=0
WARNINGS=0

[[ "${VALENCE_ENV:-development}" == "production" ]] && ok "VALENCE_ENV=production" || fail "VALENCE_ENV must be production"

DEFAULT_JWT="valence-grc-enterprise-secret-CHANGE-IN-PRODUCTION-minimum-32-chars"
if [[ -z "${JWT_SECRET_KEY:-}" || "${#JWT_SECRET_KEY}" -lt 32 || "$JWT_SECRET_KEY" == "$DEFAULT_JWT" || "$JWT_SECRET_KEY" == *CHANGE* ]]; then
  fail "JWT_SECRET_KEY must be a unique secret (32+ chars, not the default)"
else
  ok "JWT_SECRET_KEY rotated"
fi

[[ "${VALENCE_SHOW_DEMO_CREDENTIALS:-false}" == "false" ]] && ok "Demo credentials hidden" \
  || fail "VALENCE_SHOW_DEMO_CREDENTIALS must be false"
[[ "${VALENCE_SEED_DEMO_USERS:-false}" == "false" ]] && ok "Demo user seeding disabled" \
  || fail "VALENCE_SEED_DEMO_USERS must be false"

if [[ "${DATABASE_URL:-}" == postgresql+asyncpg://* ]] && ! contains_placeholder "${DATABASE_URL:-}"; then
  ok "PostgreSQL configured"
else
  fail "DATABASE_URL must use postgresql+asyncpg:// and not contain placeholder values"
fi

if [[ "${REDIS_URL:-}" == redis://* ]] && ! contains_placeholder "${REDIS_URL:-}"; then
  ok "Redis configured"
else
  fail "REDIS_URL is required and must be redis://..."
fi

if [[ -n "${CORS_ALLOWED_ORIGINS:-}" ]] && [[ "${CORS_ALLOWED_ORIGINS}" != *localhost* ]] && [[ "${CORS_ALLOWED_ORIGINS}" == *https://* ]]; then
  ok "CORS restricted to production HTTPS domain(s)"
else
  fail "CORS_ALLOWED_ORIGINS must list your HTTPS domain(s) only (no localhost)"
fi

if [[ -n "${VALENCE_PUBLIC_URL:-}" ]] && [[ "${VALENCE_PUBLIC_URL}" == https://* ]] && ! contains_placeholder "${VALENCE_PUBLIC_URL}"; then
  ok "VALENCE_PUBLIC_URL set"
else
  fail "VALENCE_PUBLIC_URL must be set to your HTTPS app URL"
fi

if [[ -n "${AUTH_OIDC_REDIRECT_URI:-}" ]] && [[ "${AUTH_OIDC_REDIRECT_URI}" == https://* ]] && ! contains_placeholder "${AUTH_OIDC_REDIRECT_URI}"; then
  ok "OIDC redirect URI is HTTPS"
else
  warn "AUTH_OIDC_REDIRECT_URI missing/placeholder (required if SSO enabled)"
fi

if [[ -n "${SMTP_HOST:-}" && "${SMTP_HOST}" != "smtp.example.com" && -n "${SMTP_USER:-}" && -n "${SMTP_PASS:-}" ]] && ! contains_placeholder "${SMTP_HOST:-}${SMTP_USER:-}${SMTP_PASS:-}"; then
  ok "SMTP configured"
else
  warn "SMTP not configured — scheduled report emails will not send"
fi

[[ "${VALENCE_FORCE_HSTS:-false}" == "true" ]] && ok "HSTS enabled" || warn "Set VALENCE_FORCE_HSTS=true behind HTTPS"

[[ "${VALENCE_PEN_TEST_ATTESTED:-false}" == "true" ]] && ok "Pen test attested" \
  || warn "External pen test not attested (VALENCE_PEN_TEST_ATTESTED)"

echo ""
if [[ "$ERRORS" -gt 0 ]]; then
  echo "$ERRORS critical issue(s), $WARNINGS warning(s). Fix before production launch."
  exit 1
fi
echo "Production configuration OK ($WARNINGS warning(s)). Deploy with: docker compose --profile production up -d"
exit 0
