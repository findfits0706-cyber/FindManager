# ADR 0011: Shift Request Collection

## Status

Accepted

## Context

Phase 7 collects staff shift preferences before monthly shift creation. Staff need to save drafts, submit requests, and see returned submissions without exposing another staff member's requests. Managers need period control, submission review, return/lock actions, and warnings when monthly shifts conflict with submitted requests.

## Decision

- Store request periods, submissions, and items in the existing `shifts` app.
- Keep one active `ShiftRequestPeriod` per location/year/month.
- Scope staff self-service APIs to `request.user` and reject staff query parameters.
- Treat the open period window and submission status as the edit boundary for staff.
- Allow managers to return submitted or locked submissions so staff can resubmit while the period is open.
- Use submitted and locked request items as advisory warnings in monthly assignment validation, monthly matrix responses, and template preview.
- Keep day-off requests separate from paid leave or absence workflows.
- Exclude published shift change requests from this phase.

## Consequences

Staff cannot view or edit another person's request through the self-service API. Managers can collect preferences without making them hard constraints, so monthly shifts remain editable even when a request is violated. Future leave, absence, and published-shift-change workflows can be added separately without overloading shift request submissions.
