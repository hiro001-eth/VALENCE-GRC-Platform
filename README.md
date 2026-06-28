# VALENCE

## Enterprise Security Metrics, Risk Quantification, and Continuous Compliance

VALENCE is an audit-grade Governance, Risk, and Compliance (GRC) platform that connects security information and event management (SIEM) telemetry to executive-ready metrics, control evidence, and tamper-evident reporting. The platform is designed for security operations, compliance officers, and executive leadership teams who require quantitative risk visibility.

VALENCE implements the Factor Analysis of Information Risk (FAIR) methodology to convert raw security events into financial risk exposure, enabling informed decision-making for non-technical executives and technical practitioners alike.

---

## Table of Contents

1. [Executive Overview](#executive-overview)
2. [What is GRC and Why Does it Matter](#what-is-grc-and-why-does-it-matter)
3. [Key Capabilities](#key-capabilities)
4. [The FAIR Risk Model Explained](#the-fair-risk-model-explained)
5. [System Architecture](#system-architecture)
6. [Quick Start Guide](#quick-start-guide)
7. [Operational Controls and Compliance Frameworks](#operational-controls-and-compliance-frameworks)
8. [CLI Reference](#cli-reference)
9. [Development and Verification](#development-and-verification)
10. [License](#license)

---

## Executive Overview

For business executives, board members, and security leaders, managing cybersecurity is no longer about checking boxes on a compliance sheet. It is about understanding the financial impact of security incidents and optimizing safety budgets.

VALENCE addresses this by linking technical security signals directly to financial risk models. Rather than stating that your firewall is ninety percent compliant, VALENCE calculates the Annual Loss Expectancy (ALE) and Value at Risk (VaR) based on real-time event telemetry.

---

## What is GRC and Why Does it Matter

### Governance
Governance is the set of rules, practices, and processes by which a company directs and controls its security operations. It ensures that security activities align with broader business objectives.

### Risk Management
Risk Management is the process of identifying, assessing, and controlling threats to an organization's capital and earnings. VALENCE uses quantitative models to calculate these risks in actual monetary values.

### Compliance
Compliance involves adhering to external laws, regulations, and industry standards such as SOC 2, ISO 27001, and NIST CSF. VALENCE automates the collection of evidence needed to prove compliance to auditors, reducing manual workloads.

---

## Key Capabilities

| Capability | Technical Detail | Business Value |
| :--- | :--- | :--- |
| **SIEM-Native Telemetry** | Automated Ingestion from Elastic, Splunk, Azure Sentinel, and Wazuh. | Real-time posture tracking based on actual telemetry, eliminating manual spreadsheets. |
| **Quantitative Risk Modeling** | Monte Carlo simulations applying the FAIR framework to calculate loss exposure. | Clear financial metrics representing risk in dollars, enabling cost-benefit decisions. |
| **Cryptographic Evidence Chain** | SHA-256 hash chaining of all metric evaluations and compliance reports. | Tamper-evident evidence collection that simplifies third-party audits. |
| **Multi-Framework Mapping** | Automatic control mapping across SOC 2, ISO 27001, NIST CSF, and PCI DSS. | Build once and comply with many standards simultaneously. |
| **Continuous Control Monitoring** | Real-time automated testing of security controls against ingestion data. | Instant visibility into security gaps before they become breaches. |

---

## The FAIR Risk Model Explained

The Factor Analysis of Information Risk (FAIR) framework is the international standard for quantitative risk analysis. VALENCE implements this model through a simulator that models security events mathematically.

### The Threat Event Frequency (TEF)
We model threat event frequency using a Poisson distribution. This calculates the probability of a specific number of security incidents occurring within a given timeframe.

### The Loss Event Magnitude (LEM)
We model the financial impact of an incident using a Log-Normal distribution. This reflects the reality that most security incidents have low to moderate costs, while a small percentage result in high financial losses.

### Monte Carlo Simulations
VALENCE runs one thousand simulations for each control metric. The output provides:
* **Annual Loss Expectancy (ALE):** The average expected financial loss per year.
* **Value at Risk (VaR):** The worst-case financial loss scenario at a ninety-five percent confidence level.

This quantitative approach enables non-technical decision-makers to prioritize security investments based on return on investment (ROI).

---

## System Architecture

VALENCE consists of three primary layers:

1. **Ingestion Layer:** Connectors pull security logs and configurations from cloud systems and SIEM hosts.
2. **Processing Layer:** Pure function pipelines validate schemas, verify data freshness, and execute FAIR calculations.
3. **Presentation Layer:** A responsive web dashboard displays real-time risk scores, compliance posture, and exports cryptographic PDF reports.

Data is stored locally in SQLite for development, with full support for PostgreSQL in production environments.

---

## Quick Start Guide

### For Non-Technical Users and Business Evaluators

The easiest way to explore VALENCE is using our pre-configured Docker stack. This boots the dashboard with simulated data representing multiple enterprise organizations.

1. Ensure Docker and Docker Compose are installed on your computer.
2. Clone this repository to your local directory.
3. Execute the startup command:
   ```bash
   docker compose --profile production up -d
   ```
4. Open your web browser and navigate to:
   ```
   http://localhost:80
   ```
5. Log in using one of the demo accounts provided on the login page (for example, username `admin` with password `valence123`).

### For Developers and Engineers

To set up a local development environment:

1. Install Python 3.11 or higher.
2. Initialize the environment:
   ```bash
   ./scripts/setup_dev.sh
   ```
3. Copy the template configuration file:
   ```bash
   cp .env.example .env
   ```
4. Start the platform:
   ```bash
   ./run.sh
   ```
5. Access the API documentation at:
   ```
   http://localhost:8000/docs
   ```

---

## Operational Controls and Compliance Frameworks

VALENCE automatically maps telemetry to control criteria across the following standards:

* **SOC 2 Type II:** Trust Services Criteria for Security, Availability, and Confidentiality.
* **ISO/IEC 27001:2022:** Information security management systems requirements.
* **NIST CSF v2.0:** National Institute of Standards and Technology Cybersecurity Framework.
* **PCI DSS v4.0:** Payment Card Industry Data Security Standard.
* **DORA:** Digital Operational Resilience Act.
* **CMMC:** Cybersecurity Maturity Model Certification.

---

## CLI Reference

The platform includes a CLI tool for automation and headless operations. Activate your virtual environment and use the following commands:

| Command | Action |
| :--- | :--- |
| `python -m grc_dashboard.main generate` | Run the metrics collection and risk simulation pipeline. |
| `python -m grc_dashboard.main export [run_id]` | Generate and repair cryptographic compliance report PDFs. |
| `python -m grc_dashboard.main validate` | Verify configuration schemas and collector connections. |
| `python -m grc_dashboard.main audit` | Print the cryptographic SHA-256 lineage hash logs. |

---

## Development and Verification

Run the verification scripts before publishing code modifications:

### Running the Test Suite
VALENCE includes a comprehensive suite of eighty-one tests covering APIs, risk engines, and collectors.
```bash
pytest tests/
```

### Formatting and Linting
We enforce strict style checks and typing:
```bash
ruff check src tests
mypy src/grc_dashboard
```

### Public Repository Boundary Checks
To ensure dev tools or test data do not leak into the public build:
```bash
./scripts/verify_public_repo.sh
```

---

## License

VALENCE is released under the MIT License. Details can be found in the LICENSE file.
