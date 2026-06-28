# Operational Runbook: VALENCE

## 1. Prerequisites and System Requirements
- **OS**: Linux (Debian 12+ or RHEL 9+)
- **Runtime**: Python >= 3.11 with `uv` package manager installed.
- **System Memory**: 2GB minimum (Peak memory constrained to 512MB per pipeline execution).
- **Dependencies**: Docker (if running containerized) or WeasyPrint system dependencies (Pango, cairo) for bare-metal PDF export.
- **Access**: Read-only SIEM API credentials, MITRE TAXII access (HTTPS port 443).

## 2. Initial Deployment Steps
1. Clone repository and navigate to `GRC-Metrics-Dashboard/`.
2. Execute `./scripts/setup_dev.sh` to initialize the `uv` virtual environment and run strict `mypy`/`ruff` checks.
3. Copy `.env.example` to `.env` and populate `SIEM_BASE_URL` and `SIEM_API_KEY`.
4. Validate pipeline configuration: `python -m grc_dashboard.main validate --quick-check`.
5. Run full pipeline: `./scripts/run_dashboard.sh generate`.

## 3. Cron Configuration
- **Recommended Schedule**: Every 4 hours (e.g., `0 */4 * * *`).
- **Justification**: 4 hours aligns well with standard SOC operational shifts, provides adequately fresh trend data without exhausting SIEM query quotas, and aligns with the `SIEM_DATA_TTL_MINUTES` defaults for cache eviction.

## 4. Log Monitoring
Structured JSON Lines logs are output to `stdout` and `/output/valence_audit.log`. Alerting thresholds:
- `METRIC_STALE`: Alert if count > 0. Indicates SIEM lag.
- `SIEM_QUERY_FAILED`: Alert if count > 2 within 1 hour. Indicates API degradation.
- `THRESHOLD_VIOLATION`: Informational. Tracks metrics moving into Red zone.
- `COVERAGE_GAP_DETECTED`: Weekly digest to Detection Engineering.

## 5. Incident Response
**Pipeline Exit Codes**:
- **Exit 0 (Success)**: Pipeline completed. No action required.
- **Exit 1 (Pipeline Failure)**: Fatal stage failure (e.g., 401 Unauthorized, Schema Drift). 
  - *Action*: Check structlog for `DashboardBaseException`. If `SIEMSchemaValidationError`, quarantine raw payload and update Pydantic models.
- **Exit 2 (Audit Failure)**: Pipeline succeeded, but outputs violated strict lineage rules (e.g., `null_rate` violation, missing footer hashes).
  - *Action*: Dashboard is suppressed. Re-run `./scripts/validate_output.sh` to manually dump the corruption source. Revert threshold configs.

## 6. Auditor Guide
**Tracing Metric Values to SIEM Query**:
1. Open the exported PDF. Navigate to the footer text.
2. Locate the `dashboard_run_id` and `metric_snapshot_hash`.
3. Query the `valence_audit.log` for the exact `dashboard_run_id`.
4. The JSON Line will contain the `siem_query_hash`.
5. Recompute the `query_hash` using the exact `MetricDefinition` stored in the Git history for that timestamp. Match hashes to prove zero-tampering.

## 7. Performance Tuning
- **Max Results Per Page**: Default 10,000. Decrease to 5,000 if OOM observed, increase to 20,000 for faster Elasticsearch scrolls.
- **Query Timeout**: Set `SIEM_QUERY_TIMEOUT_SECONDS=300`. If timeouts trigger, lower to 150 to force earlier time-range splitting via circuit breaker logic.

## 8. Rollback Procedure
If threshold boundaries are deployed incorrectly:
1. Identify the previous valid `threshold_config_hash` from the audit log.
2. Run `python -m grc_dashboard.main validate --revert <hash>`.
3. The `ThresholdVersionManager` will restore the atomic file lock and swap the YAML config.
4. Execute `python -m grc_dashboard.main generate` to flush metrics.

## 9. SSO Setup (Azure Entra ID / Okta)

VALENCE supports OIDC SSO via `/api/auth/sso/*`. The login page shows **Sign in with SSO** when configuration is complete.

### Quick check
```bash
curl http://localhost:8000/api/auth/sso/setup | jq
```
Returns the operator checklist, required env vars, and whether SSO is fully configured.

### Microsoft Entra ID (recommended)
1. **Entra admin center** → App registrations → New registration.
2. **Redirect URI (Web):** `https://<your-domain>/api/auth/sso/callback`
   - Docker/nginx default: `https://localhost/api/auth/sso/callback`
3. **Certificates & secrets** → create a client secret.
4. **App roles (optional):** create roles named `admin`, `ciso`, `analyst`, `auditor` and assign users/groups.
5. Set in `.env`:
```bash
AUTH_SSO_ENABLED=true
AUTH_SSO_PROVIDER=azure
AUTH_AZURE_TENANT_ID=<tenant-guid-from-entra-overview>
AUTH_OIDC_CLIENT_ID=<application-client-id>
AUTH_OIDC_CLIENT_SECRET=<client-secret>
AUTH_OIDC_REDIRECT_URI=https://<your-domain>/api/auth/sso/callback
```
6. Restart API. Users click **Sign in with SSO** on the login page.

**Group mapping (alternative to app roles):**
```bash
AUTH_SSO_GROUP_ROLE_MAP=Valence-Admins:admin,Valence-Auditors:auditor
```

### Okta
1. **Applications** → Create App Integration → OIDC → Web.
2. **Sign-in redirect URI:** same as above.
3. Set in `.env`:
```bash
AUTH_SSO_ENABLED=true
AUTH_SSO_PROVIDER=okta
AUTH_OKTA_DOMAIN=your-org.okta.com
AUTH_OKTA_AUTH_SERVER=default
AUTH_OIDC_CLIENT_ID=<okta-client-id>
AUTH_OIDC_CLIENT_SECRET=<okta-client-secret>
AUTH_OIDC_REDIRECT_URI=https://<your-domain>/api/auth/sso/callback
```
4. Add `groups` claim to the ID token if using group-based role mapping.

### Production SSO notes
- Use HTTPS end-to-end; redirect URI must match exactly.
- Rotate `JWT_SECRET_KEY` and OIDC client secrets via your secrets manager.
- **Redis is required** for multi-replica deployments (SSO exchange codes, login rate limits, account lockout).
- Set `VALENCE_ENV=production` and rotate sandbox passwords via `VALENCE_DEMO_PASSWORD` or `data/demo_credentials.json`.
- Hide login-page credential hints: `VALENCE_SHOW_DEMO_CREDENTIALS=false` (default in production).

### SSO + Team Access workflow (recommended)
1. Organization admin registers workspace or is seeded as first admin.
2. Admin invites team members in **Team Access** with email matching their IdP identity.
3. Users sign in with **password** (first login) or **SSO** if email matches an invited account.
4. By default `AUTH_SSO_AUTO_PROVISION=false` — unknown SSO users are rejected with a clear message.
5. For single-tenant pilots only, operators may set `AUTH_SSO_AUTO_PROVISION=true` and `AUTH_SSO_DEFAULT_TENANT=<org-slug>`.

### Per-tenant SIEM (production orgs)
1. Admin opens **SIEM Connectors** → saves Elastic/Splunk URL + API key for their organization only.
2. Click **Run pipeline now** or wait for the 5-minute scheduler.
3. Each tenant's metrics are stored under `output/tenants/<tenant_id>/metrics_history.json`.
4. Alternatively upload CSV/JSON logs — sets connector mode to `CSV` and builds metrics from uploads.

## 10. Multi-Replica Production Deployment (HA)

VALENCE supports horizontal scaling when **PostgreSQL** and **Redis** are configured.

### Architecture
```
                    ┌─────────────┐
   Users ──────────►│ Load Balancer│ (TLS termination)
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
      ┌─────────┐    ┌─────────┐    ┌─────────┐
      │ API #1  │    │ API #2  │    │ API #N  │
      └────┬────┘    └────┬────┘    └────┬────┘
           │               │               │
           └───────────────┼───────────────┘
                           ▼
              ┌────────────────────────┐
              │ PostgreSQL (primary)   │
              │ Redis (shared state)   │
              └────────────────────────┘
```

### Required environment (all replicas)
```bash
VALENCE_ENV=production
VALENCE_RELOAD=false
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/valence_grc
REDIS_URL=redis://redis:6379/0
JWT_SECRET_KEY=<from-secrets-manager>
VALENCE_FORCE_HSTS=true

# Sandbox (pilots only — disable for paying customers)
VALENCE_SEED_DEMO_USERS=true
VALENCE_SHOW_DEMO_CREDENTIALS=false
VALENCE_DEMO_PASSWORD=<rotated-or-use-credentials-file>
```

### What Redis backs
| Feature | Key prefix | Notes |
|---------|------------|-------|
| SSO exchange codes | `valence:sso:exchange:` | 120s TTL |
| Login IP rate limit | `valence:rl:ip:` | Per-IP sliding window |
| Account lockout | `valence:rl:lock:` | After 5 failures (configurable) |

### Docker Compose (production profile)
Use the included `docker-compose.yml` with `redis` and `db` services. Scale API:
```bash
docker compose up -d --scale api=3
```

### Health checks
- `GET /api/health` — liveness
- `GET /api/status` — pipeline scheduler + tenant cache stats

### Sticky sessions
**Not required** when `REDIS_URL` is set. JWTs are stateless; tenant context is derived per request.

### Pre-launch checklist
Run `./scripts/validate_production.sh` after copying `.env.production.example` → `.env`.

- [ ] `./scripts/validate_production.sh` passes (JWT, Postgres, Redis, CORS, demo creds hidden)
- [ ] `GET /api/health/readiness` returns `"production_ready": true`
- [ ] External penetration test scheduled (see `docs/compliance/PENETRATION_TEST_READINESS.md`)
- [ ] Set `VALENCE_PEN_TEST_ATTESTED=true` after pen test remediation
- [ ] `VALENCE_SHOW_DEMO_CREDENTIALS=false`
- [ ] Default dev passwords rotated / `VALENCE_SEED_DEMO_USERS=false` for paying customers
- [ ] `CORS_ALLOWED_ORIGINS` restricted to your domain
- [ ] Real TLS certificates mounted in `nginx/certs/` (not self-signed)
- [ ] SMTP env vars set for scheduled reports
- [ ] SOC 2 control matrix reviewed (`docs/compliance/SOC2_CONTROL_MATRIX.md`)

