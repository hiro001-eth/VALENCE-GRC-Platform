# External Penetration Test — Readiness Checklist

**Status:** Deferred until controlled pilot completion (per product roadmap).  
**Target window:** Weeks 4–8 before enterprise GA.

## Scope (recommended)

### In scope
- VALENCE API (`/api/*`) — authentication, authorization, tenant isolation
- WebSocket (`/ws/live`) — token validation
- OIDC SSO callback flow
- Organization registration (`POST /api/tenants/register`)
- Rate limiting and account lockout bypass attempts
- IDOR / cross-tenant data access
- Evidence chain tampering attempts

### Out of scope (unless agreed)
- Customer SIEM infrastructure
- Cloud provider infrastructure (shared responsibility)
- Physical security
- Social engineering of customer employees

## Pre-test hardening (complete before engagement)

| Item | Status |
|------|--------|
| Rate limiting + account lockout on login | Implemented |
| JWT tenant binding middleware | Implemented |
| WebSocket auth required | Implemented |
| Production sandbox password rotation | Implemented |
| Security response headers | Implemented |
| Redis for multi-replica shared state | Implemented |
| Remove hardcoded demo bypass in frontend | Implemented |
| CORS restricted to production domain | Enforced at startup + validate_production.sh |
| `JWT_SECRET_KEY` rotated from default | Enforced at startup + validate_production.sh |
| PostgreSQL + Redis in production | Enforced at startup |
| Production readiness API | `GET /api/health/readiness` |
| WAF / rate limit at edge (optional) | Recommended |

## Test credentials

Provide pen testers:
- One **demo sandbox** account (rotated password from `data/demo_credentials.json`)
- One **registered org** admin (isolated tenant)
- SSO test tenant (if SSO enabled)

**Do not** provide production customer tenant access.

## Deliverables expected from vendor

1. Executive summary (confidential)
2. Technical findings with CVSS scores
3. Remediation recommendations
4. Retest window for critical/high findings

## Post-test process

1. Triage findings within 5 business days
2. Critical/high: patch within 14 days
3. Medium: patch within 30 days
4. Update `SECURITY.md` with disclosure timeline if applicable
5. Re-run full test suite + targeted regression tests

## Suggested vendors (operator selects)

- NCC Group, Bishop Fox, Cobalt, Synack, or regional CREST-certified firm

## Evidence for SOC 2

Store pen-test report and remediation tickets as **CC4.1 / CC7.1** evidence for Type II audit.
