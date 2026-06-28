# Security Policy — VALENCE GRC Platform

## Supported versions

| Version | Supported |
|---------|-----------|
| 2.0.x   | Yes       |
| < 2.0   | No        |

## Reporting a vulnerability

**Do not** open public GitHub issues for security vulnerabilities.

Email: **katuwalmanjil609@gmail.com** (replace with your security alias before external launch)

Include:
- Affected component (API, frontend, auth, tenancy)
- Steps to reproduce
- Impact assessment
- Suggested fix (optional)

We aim to acknowledge reports within **2 business days** and provide a remediation timeline within **10 business days** for critical issues.

## Security controls (platform)

| Control | Implementation |
|---------|----------------|
| Authentication | JWT access + refresh tokens; bcrypt password hashing |
| SSO | OIDC (Azure Entra ID, Okta, generic) |
| Brute-force protection | IP rate limiting + per-account lockout (Redis-backed) |
| Tenant isolation | JWT `tenant_id` binding; demo users limited to demo tenants |
| Transport | HTTPS + HSTS (when `VALENCE_FORCE_HSTS=true`) |
| Headers | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` |
| Audit lineage | SHA-256 evidence chain for metric snapshots |
| Secrets | Env-based; rotate `JWT_SECRET_KEY`, OIDC secrets, sandbox passwords |

## Production deployment requirements

1. Set `VALENCE_ENV=production`
2. Configure `DATABASE_URL` (PostgreSQL) and `REDIS_URL`
3. Rotate `JWT_SECRET_KEY` and sandbox passwords (`VALENCE_DEMO_PASSWORD`)
4. Set `VALENCE_SHOW_DEMO_CREDENTIALS=false`
5. Restrict `CORS_ALLOWED_ORIGINS`
6. Complete external penetration test before enterprise GA (see `docs/compliance/PENETRATION_TEST_READINESS.md`)

## External penetration testing

Scheduled before paid enterprise launch. Scope and readiness checklist: `docs/compliance/PENETRATION_TEST_READINESS.md`.

## Compliance documentation

- SOC 2 control matrix: `docs/compliance/SOC2_CONTROL_MATRIX.md`
- Privacy & data retention: `docs/compliance/PRIVACY_AND_DATA_RETENTION.md`
