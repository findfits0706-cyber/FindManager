# Architecture

## System Overview

- Backend: Django + Django REST Framework
- Frontend: React + Vite
- Database: PostgreSQL for CI and production, SQLite for local development

## Authentication

- Session authentication with HttpOnly cookies
- CSRF token bootstrap via `/api/v1/auth/csrf/`
- Frontend reads current user state from `/api/v1/auth/me/`

## Backend Apps

- `apps.accounts`
  - Custom user model
  - Role/group management
  - Login, logout, password change
  - Staff CRUD with soft deactivation
- `apps.common`
  - Health check
  - Standard pagination
  - Audit events
- `apps.operations`
  - Locations
  - Work areas
  - Work categories
  - Work types and availability
  - Staff locations
  - Staff capabilities
  - My capabilities
- `apps.shifts`
  - Shift patterns
  - Shift pattern segments
  - Weekly shift templates
  - Weekly template entries
  - Monthly shift plans
  - Monthly shift assignments
  - Monthly shift segments
  - Monthly shift publications and staff self-service snapshots
  - Shift request periods, submissions, and request items
  - Shift change requests for published shifts
  - Attendance records, immutable attendance events, and attendance correction requests
  - Attendance closing periods, record snapshots, and staff monthly summaries
  - Staff compensation profiles, allowance assignments, and labor cost estimate snapshots

## Phase 2 Domain Rules

- Master data is deactivated instead of deleted.
- Historical staff assignment and capability records remain referentially valid even when master data becomes inactive.
- Only `system_admin` can manage operational masters.
- `system_admin` and `shift_manager` can manage staff locations and staff capabilities.
- `supervisor` has read-only access to operational master and assignment data.
- `staff` and `viewer` can only access their own staff assignment/capability records and active master data.

## Frontend Structure

- Staff account management pages
- Operational master pages
- Staff assignment pages
- Self-service capability page
- Shift pattern and weekly template pages
- Monthly shift planning page
- Daily/weekly shift timeline page
- Monthly attendance closing page and self-service monthly attendance page
- Labor cost estimate pages for rates, allowances, and monthly estimate review
- Labor cost budget and planned-versus-actual variance management page

## Phase 3 Domain Rules

- Shift patterns define a reusable one-day work sequence for one staff member.
- Weekly shift templates assign active shift patterns to staff by weekday, Monday through Sunday.
- Segment times are stored as offset minutes from midnight, not as `time` fields, so next-day work can be represented without introducing dated monthly shifts.
- Segment offsets must be in 15-minute increments and each active pattern must have at least one active segment.
- Removed segments and weekly entries are soft-deactivated rather than physically deleted.
- StaffCapability is not required when saving weekly templates because templates do not have concrete dates. Phase 4 validates dated StaffLocation and StaffCapability records when templates are expanded into monthly shifts.

## Phase 4 Domain Rules

- MonthlyShiftPlan is unique for active location/year/month combinations.
- MonthlyShiftAssignment is unique for active plan/date/staff combinations.
- MonthlyShiftSegment copies the selected pattern segments into dated assignment rows and stores WorkType/WorkArea snapshots.
- Template generation supports `skip_existing` and `replace_template_generated`; manual and customized assignments are protected from replacement.
- `strict` generation rejects the whole apply if any candidate has an error. `skip_invalid` applies only valid candidates.
- StaffLocation and StaffCapability are validated against each assignment work date. `assisted` and `trainee` capabilities are warnings; missing required capability is an error.
- The monthly matrix is staff-by-date. 15-minute day/week timeline views and advanced cross-location conflict detection are later phases.

## Phase 5 Domain Rules

- Timeline viewing is read-only and uses saved MonthlyShiftAssignment and MonthlyShiftSegment rows.
- The daily and weekly views share `/api/v1/monthly-shift-plans/{id}/timeline/` with a maximum effective range of seven days.
- Timeline display values come from assignment and segment snapshots, not current WorkType or WorkArea names.
- Segment offsets remain minute offsets from the assignment start date, so next-day work stays on the starting date row.
- Overlapping segments are assigned deterministic lanes so bars do not fully overlap.
- Capability warnings reuse the monthly assignment capability lookup and are returned as `warning_count`.
- The frontend draws 15-minute and hourly grid lines with CSS backgrounds instead of rendering cells for every staff/day/slot.
- Printing uses the browser print dialog and print CSS; server-side PDF generation is outside the phase.
- Timeline bars open detail only. Editing remains in the monthly shift screen.

## Shift Publication

- Monthly shift plans move through `draft`, `confirmed`, and `published`.
- Confirmed and published plans are locked against monthly plan, assignment, segment, and template-generation edits.
- Publishing creates immutable assignment and segment snapshots under `MonthlyShiftPublication`.
- Staff self-service uses `/api/v1/my-published-shifts/` and is scoped to the authenticated user.

## Shift Requests

- Shift request periods are unique for active location/year/month combinations.
- Staff request submissions move through `draft`, `submitted`, `returned`, and `locked`.
- Staff self-service uses `/api/v1/my-shift-request-periods/` and never accepts another staff identifier.
- Managers review request periods and submissions through `/api/v1/shift-request-periods/` and `/api/v1/shift-request-submissions/`.
- Returned submissions can be edited and resubmitted while the period is open; submitted and locked submissions are read-only to staff.
- Submitted and locked request items are used as warnings during monthly assignment validation, monthly matrix display, and template generation preview. Requests are advisory and do not block shift creation.

## Shift Change Requests

- Published shift change requests are stored as `ShiftChangeRequest` rows linked to a `MonthlyShiftPublicationAssignment`.
- Staff self-service uses `/api/v1/my-shift-change-requests/` and always scopes records to `request.user`.
- Management review uses `/api/v1/shift-change-requests/`; `system_admin` and `shift_manager` can operate, while `supervisor` is read-only.
- Open request statuses are `draft`, `submitted`, and `approved`; terminal statuses are `rejected`, `cancelled`, `applied`, and `closed`.
- Applying an approved request changes the monthly plan row, never the publication snapshot.
- After apply, the active publication is withdrawn and the plan returns to `confirmed`, so publication preview and republishing are required.
- Monthly matrix and my published shift responses include change request summaries without per-row follow-up queries.

## Attendance

- Attendance actuals are stored in `AttendanceRecord` as one active row per location, staff, and work date.
- Staff clocking creates immutable `AttendanceEvent` rows; corrections add manager adjustment or correction-applied events instead of rewriting the original clock events.
- Records can link to `MonthlyShiftPlan`, `MonthlyShiftAssignment`, `MonthlyShiftPublication`, and `MonthlyShiftPublicationAssignment` when a published shift exists.
- Published-shift assignment is preferred when staff clock in, but unscheduled work is allowed and marked with warnings.
- Actual and scheduled comparisons use the same 0-2880 offset-minute convention as shifts; raw clock timestamps remain DateTime values.
- Staff APIs are scoped to `request.user`; management APIs allow `system_admin` and `shift_manager` operations, while `supervisor` is read-only.
- Correction requests move through draft, submitted, approved, rejected, cancelled, and applied. Applying a correction updates the attendance record and leaves an immutable event.
- Confirmed attendance blocks staff clocking and staff correction requests until a manager unconfirms it.
- Payroll, wage rates, statutory break enforcement, notifications, and external clocking integrations are intentionally outside the attendance foundation.

## Attendance Monthly Closing

- Attendance closing periods are unique for active location/year/month combinations.
- Preview reads attendance records, attendance events, correction statuses, published shift snapshots, and fallback monthly shift assignments.
- `content_hash` tracks the stable operational content used for closing. `validation_fingerprint` tracks the current warning/error set shown to the manager.
- Closing requires the latest validation fingerprint. Errors block closing; warnings require explicit acknowledgement.
- Closing stores `AttendanceClosingRecordSnapshot` rows for daily details and `AttendanceClosingStaffSummary` rows for per-staff totals.
- Closed periods lock attendance mutations for the same location and work month, including clocking, manual adjustment, confirm/unconfirm, void, correction create, correction approval/rejection, and correction apply.
- Reopening changes the period to `reopened` and unlocks the month. Existing snapshots remain as history and are recreated on the next close.
- CSV export uses UTF-8 with BOM so Japanese headers and staff names open correctly in common spreadsheet tools.
- Payroll calculation, wage rates, overtime/legal judgement, paid leave, PDF, Excel, notifications, and external integrations remain outside this phase.

## Labor Cost Estimates

- Labor cost estimate APIs are management-only and require `system_admin` or `shift_manager`.
- `StaffCompensationProfile` stores staff wage-rate settings by location, staff, employment type, and effective date range. Active overlapping periods for the same location and staff are rejected.
- `StaffAllowanceAssignment` stores allowance settings by location, staff, code, allowance type, amount, and effective date range. Active overlapping periods for the same location, staff, and code are rejected.
- `LaborCostEstimatePeriod` is unique for active location/year/month combinations and can link to the matching `AttendanceClosingPeriod`.
- Preview prefers closed attendance snapshots. If the month is not closed, preview can use live attendance closing data but includes an `attendance_not_closed` warning and cannot be finalized.
- Finalize requires a closed attendance period, the latest `validation_fingerprint`, no errors, and explicit warning acknowledgement when warnings exist.
- Finalize recreates `LaborCostEstimateRecordSnapshot`, `LaborCostEstimateStaffSummary`, and `LaborCostEstimateAllowanceSnapshot` rows in one transaction.
- `content_hash` is generated from stable sorted attendance snapshot, profile, allowance, and calculation content. `validation_fingerprint` is generated from warning/error content.
- CSV export uses UTF-8 with BOM and always labels values as estimates. Finalized periods export saved snapshots; unfinalized periods export preview data.
- Attendance monthly closing responses expose only labor estimate ID/status/name for navigation. Wage amounts and estimate totals are not shown on attendance or staff self-service screens.
- Payroll finalization, payslips, taxes, social insurance, statutory premiums, paid leave balances, PDF/Excel, notifications, and external payroll/accounting integrations remain outside this phase.

## Labor Cost Budgets And Variance

- Labor cost budget APIs and `/labor-cost/budget` require `system_admin` or `shift_manager` through the shared `can_manage_labor_costs` authorization rule.
- `LaborCostBudgetPeriod` is unique for each active location/year/month and moves through `draft`, `review`, `approved`, `reopened`, and `archived`.
- Planned labor cost source priority is active `MonthlyShiftPublication`, confirmed `MonthlyShiftPlan`, then draft plan. Draft is previewable but is an approval error.
- Planned minute calculation excludes break and inactive plan segments and keeps the existing 0-2880 offset convention. Hourly values use Decimal and `ROUND_HALF_UP` per daily row.
- Monthly-fixed compensation and fixed-monthly allowances are added once per staff summary. They are never duplicated into each daily plan record.
- Approval recreates plan-record, staff, daily, and allowance snapshots in one transaction after locking the budget period, source plan/publication, assignments, segments, compensation profiles, and allowances.
- Approved variance reads planned values from snapshots. Actual estimates remain current: finalized Phase 11 snapshots are preferred, with unfinalized live preview as fallback.
- `content_hash` covers stable sorted budget, shift source, segments, compensation, allowance, planned calculation, and approval issue content. Current actual estimate values are excluded.
- `validation_fingerprint` covers only approval issues. Actual estimate availability and actual threshold messages are comparison issues and do not invalidate approval.
- List/detail/snapshot/preview/variance/CSV querysets use relation loading and bulk master lookups so query counts do not grow with staff or assignment count.
- `/labor-cost/monthly` may show budget amount and variance because it has the same restricted roles. Attendance, shift, and staff self-service screens do not expose budget or labor-cost amounts.
- Budget CSV uses UTF-8 with BOM. Formal payroll, sales, labor-cost ratio, automatic shift reduction, and automatic optimization remain outside this phase.

## Quality Gates

- Backend: `ruff`, `pytest`, `manage.py check`, `makemigrations --check`
- Frontend: `eslint`, `tsc --noEmit`, `vitest --run`, `vite build`
