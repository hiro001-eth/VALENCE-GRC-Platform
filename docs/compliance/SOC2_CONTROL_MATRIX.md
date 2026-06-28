# VALENCE Platform — SOC 2 Type II Control Matrix (Draft)

**Status:** Pilot-ready draft for friendly-customer deployments. Full Type II attestation requires 6–12 months of operating evidence and independent audit.

**Last updated:** 2025-06-23

## Trust Services Criteria mapping

| TSC | Control objective | VALENCE implementation | Evidence artifact | Owner |
|-----|-------------------|------------------------|-------------------|-------|
| CC6.1 | Logical access | JWT auth, RBAC (admin/ciso/analyst/auditor), SSO OIDC | Auth logs, role matrix | Engineering |
| CC6.2 | Registration & authorization | `POST /api/tenants/register`, admin-only user mgmt | Tenant registration audit | Product |
| CC6.3 | Credential management | bcrypt hashing, lockout, rate limiting | `auth/rate_limit.py`, Redis keys | Engineering |
| CC6.6 | System boundaries | Tenant middleware, `X-Tenant-ID` JWT validation | API middleware tests | Engineering |
| CC6.7 | Transmission security | TLS, HSTS, security headers | nginx/ingress config | DevOps |
| CC7.2 | Monitoring | structlog JSON, `/api/status`, pipeline alerts | `valence_audit.log` | SRE |
| CC7.3 | Change management | Git, CI (ruff/mypy/pytest), Alembic migrations | `.github/workflows/ci.yml` | Engineering |
| CC8.1 | Change approval | PR review, branch protection (recommended) | GitHub audit log | Engineering |
| CC9.2 | Vendor risk | SIEM/OIDC provider DPAs | Vendor register | Legal |
| A1.2 | Availability | Multi-replica + Redis HA guide | `RUNBOOK.md` §10 | DevOps |
| C1.1 | Confidentiality | Tenant data isolation, encrypted transit | Pen-test report (planned) | Security |
| P1.1 | Privacy notice | Customer DPA + privacy policy | `PRIVACY_AND_DATA_RETENTION.md` | Legal |

## Gaps before enterprise GA

| Gap | Target | Owner |
|-----|--------|-------|
| External penetration test | Week 4–6 of hardening | Security |
| Formal incident response runbook sign-off | Week 2 | SRE |
| SSO SAML (optional) | Roadmap | Engineering |
| Centralized log shipping (SIEM for platform) | Week 6–8 | DevOps |
| Annual access review automation | Week 8 | Product |

## Operating procedures (required for Type II)

1. **Quarterly** access review of admin accounts and SSO role mappings
2. **Annual** rotation of `JWT_SECRET_KEY`, OIDC client secrets, sandbox passwords
3. **Continuous** dependency scanning (Dependabot / Snyk — enable in CI)
4. **On incident** — follow `RUNBOOK.md` §5; notify customers per DPA within 72h

## Customer responsibility (shared model)

Customers are responsible for:
- IdP configuration and MFA enforcement
- SIEM credential scope (read-only)
- Data classification within their tenant
- User offboarding in their organization
