# ADR 0007: Bounded Memory Aggregation

- **Stage**: SIEM Ingestion & Metric Computation
- **Status**: Accepted

## Context

Retrieving large data ranges (e.g., 30 days of SIEM events) into memory for pandas computation triggers Out-Of-Memory errors.

## Options considered

1. Materialize all events into a single DataFrame — high OOM risk.
2. Streaming aggregation with batched processing — bounded memory. **Chosen.**

## Decision

Utilize `AsyncGenerator` to fetch SIEM pages and apply partial aggregation per batch before releasing memory. Peak memory must be O(query_result_limit).

## Consequences

Limits complex global operations requiring full datasets (e.g., global medians without approximations).

## Alignment

- Operational reliability constraint for risk management availability
- Invariant: `ANCHOR:I7_memory_bound_impossibility`
