# ADR 0002: Cryptographic Metric Lineage

- **Stage**: Metric Computation & PDF Export
- **Status**: Accepted

## Context

Executives and auditors require proof that dashboard numbers derive directly from the SIEM without manual tampering.

## Options considered

1. Include plain-text SIEM queries in exports — bloated PDFs, exposes schema logic.
2. Embed SHA-256 hashes of queries, formulas, and thresholds — highly verifiable, zero bloat. **Chosen.**

## Decision

Hash canonical SIEM queries, metric formulas, and threshold YAMLs. Embed `siem_query_hash`, `computation_formula_hash`, and `threshold_config_hash` in all downstream models and PDF footers. Reject any export where `null_rate > 0.001`.

## Consequences

Hash changes on minor syntax edits. Requires strict versioning of threshold and metric configs.

## Alignment

- ISO/IEC 27004:2016 Section 6.3
- Invariant: `ANCHOR:I2_lineage_impossibility`
