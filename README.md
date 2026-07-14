# FindManager

FindManager is an operations management system for Find Sports Club. The repository contains a Django/DRF backend and a React/Vite frontend for staff administration, operational masters, staff assignments, and capability tracking.

## Stack

- Backend: Python 3.13, Django 5.2, Django REST Framework
- Frontend: Node.js 24, React 19, Vite
- Database: PostgreSQL for CI/production, SQLite for local development

## Setup

1. Copy `.env.example` to `.env`.
1. Install backend dependencies in `backend`.
1. Install frontend dependencies in `frontend` with `npm install`.
1. Run `python manage.py migrate` in `backend`.
1. Run `python manage.py seed_dev` in `backend`.

`seed_dev` uses `DEV_SEED_PASSWORD` when it is set. Existing seeded users keep their current password unless `DEV_SEED_RESET_PASSWORDS=1` is provided.

## Development

- Backend: `python manage.py runserver`
- Frontend: `npm run dev`
- Full backend verification:
  - `ruff check .`
  - `ruff format --check .`
  - `pytest`
  - `python manage.py makemigrations --check`
  - `python manage.py check`
- Full frontend verification:
  - `npm run lint`
  - `npm run typecheck`
  - `npm run test -- --run`
  - `npm run build`

## Seed Users

- `system_admin`
- `shift_manager`
- `supervisor`
- `staff`
- `viewer`

## Phase 2 Scope

Phase 2 adds the `operations` app with these resources:

- Locations
- Work areas
- Work categories
- Work types
- Work type availability
- Staff locations
- Staff capabilities
- My capabilities

All APIs are exposed under `/api/v1/`.

## Phase 3 Scope

Phase 3 adds the `shifts` app with reusable shift settings:

- Shift patterns with ordered work segments
- Weekly shift templates with staff and weekday assignments
- Nested create/update APIs with soft deactivation of removed child rows
- Shift setting screens at `/shifts/patterns` and `/shifts/templates`

Shift segment times are stored as minutes from local midnight in 15-minute increments. Values may extend into the next day up to 2880 minutes, for example `1470` means `翌00:30`.

## Phase 4 Scope

Phase 4 adds dated monthly shift planning:

- Monthly shift plans by location, year, and month
- Template generation preview and apply APIs
- Staff-by-date monthly matrix API
- Manual assignment creation from shift patterns
- Assignment segment editing with soft-deactivated history
- StaffLocation and StaffCapability validation on concrete work dates
- Snapshot fields so existing monthly shifts keep their display values after master/template changes
- Monthly shift screen at `/shifts/monthly`

## Phase 5 Scope

Phase 5 adds daily and weekly timeline viewing and browser printing for saved monthly shifts:

- Timeline API at `/api/v1/monthly-shift-plans/{id}/timeline/`
- Daily and weekly 15-minute timeline screen at `/shifts/timeline`
- Staff, WorkType, WorkArea, assigned-only, and break filters
- Snapshot-based segment labels and colors
- Next-day work display up to 2880 minutes
- Lane placement for overlapping segments
- Detail panel with a deep link back to the monthly shift screen

Phase 6 adds shift confirmation, publication, and staff self-service viewing:

- Monthly shift workflow statuses: draft, confirmed, published
- Immutable publication snapshots for assignments and segments
- Publication preview, confirm, reopen, publish, and withdraw actions
- Staff self-service screen at `/shifts/my-published`
- Self-service API at `/api/v1/my-published-shifts/`, scoped to the authenticated user
- Browser printing with print-specific CSS

Phase 7 adds shift request collection before monthly shift creation:

- Request periods by active location, year, and month
- Staff self-service request submission at `/my/shift-requests`
- Manager request period and submission review at `/shifts/request-periods`
- Draft, submitted, returned, and locked submission states
- Day-off, unavailable, preferred-work, preferred-time, and note request items
- Monthly matrix, assignment save, and template preview warnings for submitted or locked requests
- Self-service APIs scoped to the authenticated user under `/api/v1/my-shift-request-periods/`

Phase 8 adds post-publication shift change requests:

- Staff self-service change requests at `/my/shift-change-requests`
- Change request creation from `/shifts/my-published`
- Manager/supervisor review at `/shifts/change-requests`
- Request types for drop, swap, cover, time change, assignment change, manager adjustment, and note
- Manager approval before any monthly shift is changed
- Apply flow that updates the monthly plan, withdraws the active publication snapshot, and requires republishing
- Monthly matrix and my published shift indicators for open or applied change requests
- Self-service APIs scoped to the authenticated user under `/api/v1/my-shift-change-requests/`

Phase 9 adds attendance clocking and actual work records:

- Daily `AttendanceRecord` rows linked to staff, location, and work date
- Immutable `AttendanceEvent` rows for clock-in, break, clock-out, manager adjustments, confirmation, and voiding
- Staff self-service attendance at `/my/attendance` and clock buttons on `/shifts/my-published`
- Staff correction requests under `/api/v1/my-attendance-corrections/`
- Manager/supervisor attendance review at `/attendance` and correction review at `/attendance/corrections`
- Manager actions for manual adjustment, confirm, unconfirm, void, approve, reject, and apply
- Monthly matrix, timeline, and my published shift attendance status indicators
- Payroll, wage rates, legal labor alerts, notifications, and external clocking devices remain outside this phase
