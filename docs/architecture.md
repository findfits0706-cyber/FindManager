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

## Quality Gates

- Backend: `ruff`, `pytest`, `manage.py check`, `makemigrations --check`
- Frontend: `eslint`, `tsc --noEmit`, `vitest --run`, `vite build`
