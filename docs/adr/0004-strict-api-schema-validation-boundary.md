# ADR 0004: Strict API Schema Validation Boundary

- **Stage**: SIEM Ingestion
- **Status**: Accepted

## Context

SIEM API updates or misconfigurations can alter JSON payload structures, leading to downstream computation errors or silent data drops.

## Options considered

1. Loose dictionary parsing using `.get()` — frail, fails deep in computation.
2. Strict Pydantic v2 validation at the network boundary — fails fast, exact field diagnostics. **Chosen.**

## Decision

Validate raw SIEM API responses directly into Pydantic models. Unvalidated data never advances to `MetricEngine`. Failures raise `SIEMSchemaValidationError`.

## Consequences

Any SIEM vendor update altering a mapped field breaks ingestion immediately, preventing corrupted dashboards.

## Alignment

- NIST SP 800-30 Rev.1 Section 3.1
- Invariant: `ANCHOR:I4_schema_drift_impossibility`
