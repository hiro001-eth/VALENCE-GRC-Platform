# ADR 0005: Global Exception Routing to Visual Error States

- **Stage**: Dashboard Rendering & Error Handling
- **Status**: Accepted

## Context

Swallowed exceptions or empty datasets defaulting to `0` result in a false Green state.

## Options considered

1. Graceful degradation by omitting failed cards — changes layout, hides failure.
2. Explicit visual error states for any failure — preserves layout, highlights exact failure domain. **Chosen.**

## Decision

Use `@dashboard_stage` decorator to trap unhandled exceptions, route to `DashboardErrorHandler`, log via structlog, and render an explicit error card (e.g., `NO_DATA`, `503`) instead of a fallback value.

## Consequences

Transient network errors immediately impact dashboard visuals, forcing remediation of underlying connectivity issues.

## Alignment

- NIST SP 800-30 Rev.1 Section 4.4
- Invariant: `ANCHOR:I5_silent_failure_impossibility`
