# ADR 0001: SIEM Data Freshness Validation

- **Stage**: SIEM Ingestion
- **Status**: Accepted

## Context

Dashboard metrics can be misleading if generated from stale cached data or delayed SIEM replication. Presenting stale data as healthy "Green" creates a false sense of security.

## Options considered

1. Rely on dashboard rendering time — false security, ignores SIEM delay.
2. Validate payload timestamp at generation — introduces latency but guarantees freshness. **Chosen.**

## Decision

`SIEMClient` must validate API response timestamp headers. Metric computations must record `data_freshness_utc` and explicitly flag `is_stale` when older than TTL.

## Rationale

Ensures compliance with operational reality and prevents silent degradation of security posture visibility.

## Consequences

The pipeline raises `StaleMetricException` and renders a red `STALE` banner instead of returning green metrics for delayed data.

## Alignment

- NIST SP 800-30 Rev.1 Section 4.4
- Invariant: `ANCHOR:I1_stale_data_impossibility`
