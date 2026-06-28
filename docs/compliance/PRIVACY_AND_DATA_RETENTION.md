# VALENCE — Privacy & Data Retention Program (Draft)

**Applies to:** VALENCE GRC platform (the product), not customer SIEM data classification.

**Last updated:** 2025-06-23

## Data categories

| Category | Examples | Storage | Retention |
|----------|----------|---------|-----------|
| Account data | Username, email, hashed password, role | PostgreSQL `users` | Life of contract + 30 days |
| Tenant metadata | Company name, tenant slug | PostgreSQL `tenants` | Life of contract + 30 days |
| Security metrics | KPI/KRI values, VaR, RAG status | PostgreSQL + in-memory cache | Configurable; default 24 months |
| Evidence chain | SHA-256 audit records | PostgreSQL `evidence_records` | 7 years (audit default) |
| Timeline snapshots | Historical posture | PostgreSQL `timeline_snapshots` | 24 months |
| Auth telemetry | Login success/failure (structlog) | Log aggregator | 90 days |
| SSO state | OIDC exchange codes | Redis (120s TTL) | Ephemeral |
| Threat intel cache | CISA KEV JSON | `data/cache/threat_intel/` | 1 hour TTL |

## Lawful basis (B2B SaaS)

- **Contract performance** — providing the GRC dashboard service
- **Legitimate interest** — platform security (rate limiting, audit logs)
- **Consent** — marketing communications (if opted in separately)

## Data residency

- Default: customer-selected cloud region at deployment time
- No cross-border transfer unless customer configures multi-region DR

## Sub-processors (typical deployment)

| Sub-processor | Purpose |
|---------------|---------|
| Cloud host (AWS/GCP/Azure) | Compute, storage |
| PostgreSQL provider | Persistent data |
| Redis provider | Session/rate-limit state |
| Microsoft / Okta | SSO identity (customer-controlled) |
| CISA / MITRE | Public threat intel feeds (no PII) |

## Data subject rights

For end-users of customer organizations, VALENCE acts as **processor**. Customers handle DSARs; VALENCE provides:
- User export API (roadmap)
- Account deletion on tenant offboarding
- Evidence pack export for audit (`/api/evidence/export`)

## Retention & deletion

1. **Tenant offboarding:** Delete tenant row, users, evidence, timeline within 30 days
2. **Backup retention:** 30 days rolling (configure per deployment)
3. **Logs:** 90-day default; no passwords or tokens in logs

## Security measures

See `SECURITY.md` and `SOC2_CONTROL_MATRIX.md`.

## Contact

Privacy inquiries: **privacy@valence-grc.example** (replace before launch)
