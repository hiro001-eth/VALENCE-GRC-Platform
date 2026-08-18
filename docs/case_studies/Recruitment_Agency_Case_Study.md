# VALENCE Case Study: Securing Candidate PII at a Cross-Border Recruitment Agency

## Executive Summary
A cross-border manpower recruitment agency operating in South Asia, handling thousands of candidate applications annually, is custodian to highly sensitive personally identifiable information (PII), including scans of national identity documents, passport numbers, and employment histories.

To satisfy international clients' security expectations and prepare for GDPR-aligned data regulations, the agency deployed the **VALENCE GRC Platform**. VALENCE continuously scanned the agency's infrastructure, immediately flagging critical compliance risks and mapping them directly to financial exposure models.

---

## The Challenge
Prior to deploying VALENCE, the agency's IT team operated without centralized compliance visibility. An automated scan by VALENCE identified three major systemic vulnerabilities:

1. **Insecure Document Storage (PII Exposure)**: Scans of candidates' identity documents were stored in a public S3 bucket without server-side encryption or access logging, leading to high risk of data leakage.
2. **Authentication Gaps**: The core portal lacked self-service password modification or credential rotation features. Both candidates and administrators relied on static credentials set at provisioning.
3. **Exposed Secrets & Lack of Cryptography**: Database credentials were stored in plaintext configuration files. Candidate PII was stored unencrypted at rest in the database.

---

## GRC Metrics & Financial Exposure Analysis
VALENCE calculated the agency's security metrics and quantified the financial risk in real-time, helping the executive team prioritize engineering resources:

* **Mean Time to Respond (MTTR)**: **480.0 minutes** (Red Status) — Handled manually, response times to potential breaches exceeded acceptable SLA thresholds.
* **Critical CVE Patch Lag**: **45.0 days** (Red Status) — Insecure database versions and framework dependencies remained unpatched.
* **Privileged Access Reviews**: **0.0%** (Red Status) — Lack of credential rotation or identity audits.
* **Annualized Loss Expectancy (ALE)**: **$318,600 USD**
* **Value-at-Risk (95% VaR)**: **$700,920 USD** (The quantified peak financial impact in the event of a candidate PII breach)
* **Probability of Breach**: **85.0%**

---

## How VALENCE Resolved the Gaps

### 1. Real-Time Risk Isolation & ITSM Orchestration
Upon detecting the unencrypted S3 bucket, VALENCE automatically created a critical-severity finding in the ITSM system, assigning it to the IT Infrastructure Lead. The finding included step-by-step remediation commands to restrict bucket access and enforce AES-256 server-side encryption.

### 2. Enforcing Cryptographic Standards
VALENCE's compliance rules scanned the application configurations, triggering a finding that recommended encrypting database connection strings and implementing AES-256 field-level encryption for database fields containing candidate PII.

### 3. Enabling Self-Service Access Controls
Following the creation of the access control finding, the engineering team integrated secure self-service password modifications and restricted default admin accounts.

---

## Results & Business Impact
By using VALENCE to track, monitor, and remediate these issues:
* **PII Risk Eliminated**: 100% of identity and passport document scans are now encrypted at rest with strict IAM policies.
* **MTTR Decreased**: Automated alerting lowered response SLAs from 480 minutes to under 15 minutes.
* **Credibility Secured**: The agency generated a verified, cryptographically signed GRC report PDF using VALENCE's evidence chain to present to international clients as proof of compliance.
* **95% VaR Reduced**: The overall Value-at-Risk dropped from **$700,920 USD** to under **$45,000 USD** within two weeks of deployment.
