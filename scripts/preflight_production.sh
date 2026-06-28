#!/usr/bin/env bash
# Connectivity + runtime preflight checks before launch.
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${1:-.env}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

fail() { echo "FAIL: $1"; ERRORS=$((ERRORS + 1)); }
ok() { echo "OK:   $1"; }
warn() { echo "WARN: $1"; WARNINGS=$((WARNINGS + 1)); }

ERRORS=0
WARNINGS=0

if command -v python3 >/dev/null 2>&1; then
  python3 - <<'PY' || exit 1
import os
import socket
import sys
from urllib.parse import urlparse

errors = []

db = os.getenv("DATABASE_URL", "")
redis = os.getenv("REDIS_URL", "")

for label, url in [("database", db), ("redis", redis)]:
    if not url:
        errors.append(f"{label} URL missing")
        continue
    parsed = urlparse(url)
    if not parsed.hostname or not parsed.port:
        errors.append(f"{label} URL missing host/port: {url}")
        continue
    try:
        with socket.create_connection((parsed.hostname, parsed.port), timeout=3):
            print(f"OK:   {label} reachable ({parsed.hostname}:{parsed.port})")
    except OSError as exc:
        errors.append(f"{label} unreachable ({parsed.hostname}:{parsed.port}): {exc}")

if errors:
    for err in errors:
        print(f"FAIL: {err}")
    sys.exit(1)
PY
else
  warn "python3 not found; skipping socket checks"
fi

if [[ -n "${VALENCE_PUBLIC_URL:-}" ]]; then
  if curl -fsS "${VALENCE_PUBLIC_URL}/api/health" >/dev/null 2>&1; then
    ok "Public URL responds to /api/health"
  else
    warn "Public URL not reachable yet (${VALENCE_PUBLIC_URL}/api/health)"
  fi
fi

echo ""
if [[ "$ERRORS" -gt 0 ]]; then
  echo "$ERRORS preflight failure(s), $WARNINGS warning(s)."
  exit 1
fi
echo "Preflight checks passed ($WARNINGS warning(s))."
