# ADR 0013: Attendance Records

## Status

Accepted

## Context

Published shifts describe planned work, but the system also needs actual attendance facts: clock-in, break, clock-out, manager correction, staff correction requests, and manager confirmation. These facts must not let staff inspect another staff member's attendance or rewrite clock history after the fact.

## Decision

- Store daily actuals in `AttendanceRecord`, unique per active location, staff, and work date.
- Store staff clocking and manager lifecycle actions as immutable `AttendanceEvent` rows.
- Link attendance records to monthly plans, assignments, publications, and publication assignments when a published shift exists.
- Keep published shift snapshots separate from attendance actuals. Attendance compares against the schedule but does not mutate the schedule.
- Separate manager manual adjustments from staff correction requests. Staff request a correction; managers approve and apply it.
- Allow unscheduled work records and mark them with warnings rather than blocking clock-in.
- Block staff clocking and staff correction requests after manager confirmation until the record is unconfirmed.
- Keep payroll calculation, wage rates, overtime, late-night premiums, paid leave balance, strict labor-law alerts, CSV/PDF export, notifications, GPS, QR, face recognition, and external clock devices outside this phase.

## Consequences

Attendance records provide one daily operational summary for list and monthly views, while events preserve the original facts needed for audit. Published shifts remain a plan snapshot; attendance can diverge through warnings and corrections without altering what was originally published. Managers keep final authority over confirmed records, and self-service APIs remain scoped to the authenticated staff member.
