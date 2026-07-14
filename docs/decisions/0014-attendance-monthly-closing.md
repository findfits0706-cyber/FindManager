# ADR 0014: Attendance Monthly Closing

## Status

Accepted

## Context

Phase 9 introduced daily attendance records, immutable attendance events, and correction requests. Managers now need a monthly operational checkpoint that verifies the month, records warnings/errors, locks further edits, and exports attendance facts for downstream work without turning this system into payroll.

## Decision

- Add `AttendanceClosingPeriod` as the monthly workflow object for one active location/year/month.
- Keep daily attendance mutable operational records separate from monthly closing snapshots.
- Store `AttendanceClosingRecordSnapshot` rows at close time so reopened or later-corrected attendance does not change the historical closed output.
- Store `AttendanceClosingStaffSummary` rows at close time for stable per-staff monthly totals.
- Keep `content_hash` and `validation_fingerprint` separate. The content hash represents the stable attendance/schedule/correction inputs; the validation fingerprint represents the warnings and errors the manager acknowledged.
- Allow closing with warnings only when the manager explicitly acknowledges them. Errors still block closing.
- Lock closed periods against attendance mutation, including staff clocking, manager adjustment, confirmation changes, voiding, and correction workflows.
- Export CSV as UTF-8 with BOM so Japanese column names and staff names open reliably in common spreadsheet tools.

## Non-Goals

- Payroll calculation, wage rates, allowances, and paid leave balance are not part of phase 10.
- Overtime/legal judgement and statutory alerting are not part of phase 10.
- PDF and Excel generation are not part of phase 10; CSV is the export format.
- Notifications and external integrations are not part of phase 10.

## Consequences

Closed monthly output is stable even if operational attendance is reopened and corrected later. Managers can proceed with known warnings when they intentionally acknowledge them, while true consistency errors still block closing. The lock prevents silent drift between the monthly export and the daily attendance screens. Downstream payroll or legal calculation can consume closed facts later without being coupled to the operational attendance editing workflow.
