# ADR 0003: Deterministic RAG Classification

- **Stage**: RAG Classification
- **Status**: Accepted

## Context

Manual threshold adjustments or floating-point anomalies can cause the same numerical metric to render differently on different days.

## Options considered

1. Store thresholds in mutable database rows — prone to silent mutation.
2. Define thresholds in frozen YAML config with rigorous inclusive/exclusive semantics. **Chosen.**

## Decision

`ClassificationEngine` operates as a pure function. `ThresholdConfig` is frozen post-load via Pydantic `frozen=True`. Mutation attempts raise `FrozenInstanceError`.

## Consequences

Threshold updates require a formal config deployment and version bump. No hot-fixes via UI.

## Alignment

- ISO/IEC 27004:2016 Section 7.2
- Invariant: `ANCHOR:I3_rag_determinism_impossibility`
