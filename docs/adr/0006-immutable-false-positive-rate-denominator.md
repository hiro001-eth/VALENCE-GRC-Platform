# ADR 0006: Immutable False Positive Rate Denominator

- **Stage**: Metric Computation
- **Status**: Accepted

## Context

False Positive Rates can be artificially lowered by dividing by total alerts (including unclassified ones) rather than strictly classified alerts.

## Options considered

1. Flexible denominator based on analyst preference — allows manipulation.
2. Rigid formula isolating true/false positives — analytically sound. **Chosen.**

## Decision

`FPRCalculator` strictly computes `false_positives / (false_positives + true_positives)`. Unclassified alerts are excluded from the denominator.

## Consequences

Teams must formally classify alerts to influence the FPR metric. Unclassified volumes are tracked separately.

## Alignment

- ISO/IEC 27004:2016 Section 7.3
- Invariant: `ANCHOR:I6_fpr_manipulation_impossibility`
