# Changelog

All notable changes to VALENCE GRC are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-06-26

### Added

- Enterprise GRC API with multi-tenant auth, SSO (OIDC), and role-based access
- SIEM collectors for Elastic, Splunk, and QRadar with freshness validation
- Continuous compliance monitoring across SOC 2, ISO 27001, NIST CSF, PCI DSS, FedRAMP, GDPR, CMMC
- Cryptographic metric lineage (SHA-256) in PDF exports
- Deterministic RAG classification with frozen YAML thresholds
- Integrations: Okta, AWS, GCP, GitHub, Jira, ServiceNow, Jamf, Kandji, Google Workspace
- Trust center, evidence vault, gap analyzer, and auditor marketplace APIs
- Production Docker Compose stack (PostgreSQL, Redis, Nginx)
- Architecture Decision Records (`docs/adr/`)
- Public repository boundary enforcement (ADR-0008)

### Security

- JWT access/refresh tokens with bcrypt password hashing
- IP rate limiting and per-account lockout (Redis-backed)
- Tenant isolation via JWT `tenant_id` binding
- Security policy and SOC 2 control matrix documentation

[2.0.0]: https://github.com/your-org/valence-grc/releases/tag/v2.0.0
