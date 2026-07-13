# ADR 0012: Shift Change Requests

## Status

Accepted

## Context

After a monthly shift has been published, staff may need to drop a shift, request a cover staff member, swap work, adjust time, or leave a note. The published snapshot is already visible to staff and must remain an immutable record of what was published.

## Decision

- Store post-publication change requests in the existing `shifts` app as `ShiftChangeRequest`.
- Link each request to the active `MonthlyShiftPublicationAssignment` that the staff member saw.
- Scope the staff API to `request.user` and do not accept requester or target staff identifiers from self-service requests.
- Require manager approval before any monthly shift assignment or segment is changed.
- Apply approved requests to the monthly plan only, never to the publication snapshot.
- Withdraw the active publication during apply and leave the plan in a state that requires publication preview and republishing.
- Use AuditEvent for request creation, update, submit, cancel, approve, reject, apply, and close.
- Keep staff chat, email, push, LINE, WebSocket notifications, and automatic cover selection outside this phase.
- Keep attendance facts, absence records, payroll, and paid leave balance separate from shift change requests.

## Consequences

Published snapshots remain a stable audit trail. A request always points back to the exact published assignment that triggered it, while the mutable monthly plan carries the approved correction. Managers keep final control over operational changes, and staff self-service cannot inspect or mutate another staff member's requests. Applying a request intentionally creates a difference between the last publication and the plan, so republishing is an explicit follow-up step rather than an invisible side effect.
