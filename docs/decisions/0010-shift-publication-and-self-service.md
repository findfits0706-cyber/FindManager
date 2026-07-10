# ADR 0010: Shift Publication and Self-Service

## Status

Accepted

## Context

Phase 6 separates manager editing from staff-facing shift viewing. Managers need to confirm a monthly shift, publish an immutable version, withdraw it when needed, and let staff see only the published schedule that applies to themselves.

## Decision

- Add `workflow_status` to `MonthlyShiftPlan`: `draft`, `confirmed`, and `published`.
- Lock monthly plan and assignment edits unless the plan is in `draft`.
- Compute a deterministic content hash from active assignments and segments, excluding timestamps.
- Store published shifts in `MonthlyShiftPublication`, `MonthlyShiftPublicationAssignment`, and `MonthlyShiftPublicationSegment`.
- Serve staff self-service through `/api/v1/my-published-shifts/`, always scoped to `request.user`.
- Keep publication APIs read-only outside explicit action endpoints on monthly plans.

## Consequences

Published shifts remain stable even if current draft assignments or operational masters change later. Publishing verifies that the confirmed content hash still matches the current plan, so accidental changes between confirmation and publication are rejected. Staff cannot query another staff member's schedule through the self-service API.
