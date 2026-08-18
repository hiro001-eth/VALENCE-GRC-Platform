<p align="center">
  <strong>VALENCE</strong>
</p>

<p align="center">
  <em>Enterprise Security Metrics · Quantitative Risk Modeling · Continuous Compliance</em>
</p>

<p align="center">
  <a href="https://github.com/hiro001-eth/VALENCE-GRC-Platform/actions/workflows/ci.yml"><img src="https://github.com/hiro001-eth/VALENCE-GRC-Platform/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/version-3.0.0-blue" alt="Version">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/frameworks-SOC2%20%7C%20ISO27001%20%7C%20NIST%20%7C%20PCI--DSS%20%7C%20DORA%20%7C%20NIS2-blueviolet" alt="Frameworks">
</p>

---

VALENCE is an audit-grade Governance, Risk, and Compliance (GRC) platform that connects SIEM telemetry to executive-ready metrics, control evidence, and tamper-evident reporting.

The platform implements the [FAIR](https://www.fairinstitute.org/) (Factor Analysis of Information Risk) methodology to convert raw security events into financial risk exposure — enabling informed decision-making for security operations teams, compliance officers, and executive leadership.

## Table of Contents

- [What's New in v3.0.0](#whats-new-in-v300)
- [Key Capabilities](#key-capabilities)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Compliance Frameworks](#compliance-frameworks)
- [CLI Reference](#cli-reference)
- [API Surface](#api-surface)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

---

## What's New in v3.0.0

| Feature | Description |
| :--- | :--- |
| **Breach Simulation** | Monte Carlo cascading risk propagation with what-if scenario modeling |
| **Security Maturity Model** | CMM Level 1–5 assessment with gap analysis and roadmap generation |
| **Risk Treatment Plans** | RACI matrices, remediation tracking, and control improvement workflows |
| **Audit Log** | Cryptographic integrity chain with tamper detection for full audit trail |
| **NIS2 & DORA** | Complete control mapping for EU Digital Operational Resilience |
| **Penetration Testing Suite** | 7 automated security test suites covering OWASP Top 10 |
| **Observability** | OpenTelemetry-compatible request tracing and latency histograms |
| **Notification Engine** | Multi-channel alerting via email, Slack, Teams, and webhooks |
| **Evidence Export** | ZIP-packaged evidence bundles for auditor delivery |

See the full [CHANGELOG](CHANGELOG.md) for details.

---

## Key Capabilities

| Capability | Technical Detail | Business Value |
| :--- | :--- | :--- |
| **SIEM-Native Telemetry** | Automated ingestion from Elastic, Splunk, Azure Sentinel, and Wazuh | Real-time posture tracking from actual telemetry |
| **Quantitative Risk (FAIR)** | Monte Carlo simulations (1,000 iterations per metric) calculating ALE and VaR₉₅ | Financial risk metrics enabling cost-benefit decisions |
| **Cryptographic Evidence** | SHA-256 hash chaining of all metric evaluations and compliance reports | Tamper-evident evidence for third-party audits |
| **Multi-Framework Mapping** | Automatic control mapping across 9 compliance frameworks | Build once, comply with many standards simultaneously |
| **Continuous Control Monitoring** | Real-time automated testing of security controls against ingestion data | Instant visibility into security gaps |
| **Breach Simulation** | Cascading risk propagation with Monte Carlo sampling | Quantified impact of control failures before they happen |
| **Security Maturity** | CMM L1–L5 assessment with maturity roadmaps | Measurable security program improvement tracking |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER                          │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Dashboard │  │ Trust Ctr │  │ REST API │  │ WebSocket (live) │  │
│  └──────────┘  └───────────┘  └──────────┘  └──────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│                        PROCESSING LAYER                            │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Metric   │  │ FAIR Risk │  │ RAG      │  │ Compliance       │  │
│  │ Engine   │  │ Simulator │  │ Classif. │  │ Gap Analyzer     │  │
│  └──────────┘  └───────────┘  └──────────┘  └──────────────────┘  │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Breach   │  │ Maturity  │  │ Evidence │  │ Notification     │  │
│  │ Sim.     │  │ Model     │  │ Vault    │  │ Engine           │  │
│  └──────────┘  └───────────┘  └──────────┘  └──────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│                        INGESTION LAYER                             │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Elastic  │  │ Splunk    │  │ QRadar   │  │ Azure Sentinel   │  │
│  └──────────┘  └───────────┘  └──────────┘  └──────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│                        DATA LAYER                                  │
│  ┌──────────────────┐  ┌────────────┐  ┌──────────────────────┐   │
│  │ PostgreSQL (prod)│  │ Redis      │  │ SQLite (dev)         │   │
│  │ + Alembic        │  │ (caching)  │  │                      │   │
│  └──────────────────┘  └────────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

**Data Flow:** SIEM connectors → Schema validation → Metric computation → FAIR simulation → RAG classification → Evidence vault → Dashboard + PDF export

---

## Quick Start

### Docker (Recommended)

```bash
git clone https://github.com/hiro001-eth/VALENCE-GRC-Platform.git
cd VALENCE-GRC-Platform
cp .env.example .env
docker compose --profile production up -d
```

Open `http://localhost:80` and log in with the demo credentials shown on the login page.

### Local Development

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/) package manager

```bash
git clone https://github.com/hiro001-eth/VALENCE-GRC-Platform.git
cd VALENCE-GRC-Platform
./scripts/setup_dev.sh
cp .env.example .env
./run.sh
```

API documentation available at `http://localhost:8000/docs`.

---

## Compliance Frameworks

VALENCE automatically maps telemetry to control criteria across the following standards:

| Framework | Standard | Coverage |
| :--- | :--- | :--- |
| **SOC 2 Type II** | Trust Services Criteria (Security, Availability, Confidentiality) | Full |
| **ISO/IEC 27001:2022** | Information Security Management Systems | Full |
| **NIST CSF v2.0** | Cybersecurity Framework | Full |
| **PCI DSS v4.0** | Payment Card Industry Data Security Standard | Full |
| **DORA** | Digital Operational Resilience Act (EU) | Full |
| **NIS2** | Network and Information Security Directive (EU) | Full |
| **CMMC** | Cybersecurity Maturity Model Certification (DoD) | Full |
| **FedRAMP** | Federal Risk and Authorization Management Program | Partial |
| **GDPR** | General Data Protection Regulation | Partial |

---

## CLI Reference

Activate your virtual environment, then use the following commands:

| Command | Description |
| :--- | :--- |
| `valence generate` | Run the metrics collection and risk simulation pipeline |
| `valence export [run_id]` | Generate cryptographic compliance report PDFs |
| `valence validate` | Verify configuration schemas and collector connections |
| `valence audit` | Print the SHA-256 cryptographic lineage hash logs |

---

## API Surface

VALENCE exposes a comprehensive REST API. Key endpoint groups:

| Group | Endpoints | Description |
| :--- | :--- | :--- |
| **Auth** | `/api/auth/*` | Login, token refresh, SSO OIDC, SCIM provisioning |
| **Metrics** | `/api/metrics/*` | SIEM-derived security metrics and trend data |
| **Compliance** | `/api/compliance/*` | Framework status, control mapping, gap analysis |
| **Risk** | `/api/risk/*`, `/api/whatif/*` | FAIR simulation, what-if scenarios |
| **Breach Sim** | `/api/breach-simulation/*` | Monte Carlo breach impact modeling |
| **Maturity** | `/api/maturity/*` | Security maturity assessment (CMM L1–L5) |
| **Evidence** | `/api/evidence/*` | Evidence vault and export packaging |
| **Findings** | `/api/findings/*` | Security findings with ITSM integration |
| **Reports** | `/api/reports/*` | PDF generation with cryptographic attestation |
| **Audit Log** | `/api/audit-log/*` | Tamper-evident activity logging |

Full API documentation: `http://localhost:8000/docs` (interactive Swagger UI with custom theme).

---

## Development

### Running the Test Suite

VALENCE includes comprehensive test coverage across unit, integration, security, and end-to-end layers:

```bash
# Full test suite
pytest tests/

# Security penetration tests
pytest tests/security/

# Integration tests
pytest tests/integration/

# E2E smoke tests (requires Playwright)
pytest e2e/
```

### Linting & Type Checking

```bash
ruff check src tests
mypy src/grc_dashboard
```

### Repository Boundary Checks

Ensures sensitive content does not leak into the public repository:

```bash
./scripts/verify_public_repo.sh
```

---

## Contributing

We welcome contributions. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on:
- Code style (enforced via `ruff` and `mypy`)
- Pull request process
- Testing requirements

---

## Security

For vulnerability reports, see [SECURITY.md](SECURITY.md). **Do not** open public issues for security vulnerabilities.

---

## License

VALENCE is released under the [MIT License](LICENSE).
