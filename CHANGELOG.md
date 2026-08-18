# Changelog

All notable changes to VALENCE GRC are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] - 2026-08-19

### Added

#### Risk & Simulation
- Breach simulation engine with Monte Carlo cascading risk propagation
- What-if scenario modeling for control change impact analysis
- Risk treatment plans with RACI matrices and remediation tracking
- Security maturity assessment model (CMM Level 1–5) with gap analysis

#### Compliance & Governance
- NIS2 framework support with full control mapping
- Expanded cross-framework control mapping (SOC 2, ISO 27001, NIST CSF, PCI DSS, FedRAMP, GDPR, CMMC, DORA, NIS2)
- Policy lifecycle management with attestation workflows
- Audit log with cryptographic integrity chain and tamper detection
- Evidence export with ZIP packaging for auditor delivery
- Compliance questionnaire engine with scoring

#### Platform & Infrastructure
- OpenTelemetry-compatible observability middleware (request tracing, latency histograms)
- Distributed task worker for background pipeline execution
- Notification engine (email, Slack, Microsoft Teams, webhook)
- Edge rate limiting middleware with sliding window algorithm
- SQLite-to-PostgreSQL migration tooling

#### Security Testing
- 7 penetration test suites: API security, authentication, authorization, injection, data security, infrastructure, WebSocket
- Tenant isolation integration tests
- Distributed task integration tests
- Telemetry pipeline integration tests
- Cryptographic integrity unit tests

#### API Surface
- Breach simulation API (`/api/breach-simulation`)
- Maturity assessment API (`/api/maturity`)
- Risk treatment API (`/api/risk-treatment`)
- Audit log API (`/api/audit-log`)
- Evidence export API (`/api/evidence-export`)
- Notification preferences API (`/api/notifications`)

#### Frontend
- WebGL-accelerated landing page animation
- Login page particle animation
- Swagger API documentation theme
- Trust center confidentiality agreement flow

### Changed
- Upgraded SIEM collector freshness validation with configurable TTL
- Improved JWT handler with enhanced token rotation
- Refactored SSO OIDC flow for Azure Entra ID, Okta, and generic providers
- Enhanced edge rate limiting with per-route configuration
- Improved demo scenario data for multi-tenant demonstrations
- Updated Docker Compose stack with health checks and resource constraints

### Security
- Edge rate limiting with sliding window and IP-based throttling
- Enhanced tenant isolation via JWT `tenant_id` binding enforcement
- Penetration test suite covering OWASP Top 10 attack vectors
- Cryptographic audit log with SHA-256 integrity verification
- Input validation hardening across all API endpoints

### Fixed
- Version synchronization between `pyproject.toml` and `__init__.py`
- Repository boundary enforcement for sensitive content (ADR-0008)
- Removed development artifacts and AI-generated documents from version control

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

[3.0.0]: https://github.com/hiro001-eth/VALENCE-GRC-Platform/releases/tag/v3.0.0
[2.0.0]: https://github.com/hiro001-eth/VALENCE-GRC-Platform/releases/tag/v2.0.0
