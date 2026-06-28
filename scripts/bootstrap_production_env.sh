#!/usr/bin/env bash
# Generate a production-ready .env from template with secure defaults.
set -euo pipefail
cd "$(dirname "$0")/.."

TARGET_ENV="${1:-.env.production}"
TEMPLATE=".env.production.example"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "Missing $TEMPLATE"
  exit 1
fi

if [[ -f "$TARGET_ENV" ]]; then
  echo "Refusing to overwrite existing $TARGET_ENV"
  echo "Use a new filename or remove it first."
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to generate secure secrets."
  exit 1
fi

JWT_SECRET="$(openssl rand -hex 48)"
DB_PASSWORD="$(openssl rand -hex 20)"
SMTP_PASSWORD="$(openssl rand -hex 16)"

cp "$TEMPLATE" "$TARGET_ENV"

sed -i \
  -e "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=${JWT_SECRET}|g" \
  -e "s|CHANGE_ME_DB_PASSWORD|${DB_PASSWORD}|g" \
  -e "s|^SMTP_PASS=.*|SMTP_PASS=${SMTP_PASSWORD}|g" \
  "$TARGET_ENV"

echo "Generated $TARGET_ENV with secure random defaults."
echo "Next:"
echo "  1) Replace domain fields (yourcompany.com)"
echo "  2) Configure real SMTP host/user"
echo "  3) Run ./scripts/validate_production.sh $TARGET_ENV"
