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

Phase 10 adds monthly attendance closing:

- Monthly closing periods by active location, year, and month
- Live preview with warning/error details, stable `content_hash`, and `validation_fingerprint`
- Close flow with warning acknowledgement, fingerprint match, immutable daily snapshots, and staff summaries
- Closed-month lock for clocking, manual adjustment, confirmation changes, voiding, and attendance correction workflows
- Reopen and archive actions for manager-controlled operational recovery
- Manager/supervisor screen at `/attendance/monthly`
- Staff self-service monthly attendance screen at `/my/attendance-monthly`
- UTF-8 BOM CSV export from closed snapshots or unclosed live preview
- Payroll calculation, wage rates, overtime/legal judgement, PDF, Excel, and external integrations remain outside this phase

Phase 11 adds labor cost estimate foundations:

- Staff compensation profiles with effective periods for hourly, monthly-fixed, and other employment types
- Staff allowance assignments for worked-day, worked-hour, fixed-monthly, and manual allowances
- Monthly labor cost estimate periods linked to attendance closing periods
- Preview from closed attendance snapshots, or live preview with an `attendance_not_closed` warning
- Finalize flow with warning acknowledgement, validation fingerprint match, immutable estimate snapshots, staff summaries, and allowance snapshots
- UTF-8 BOM CSV export from finalized snapshots or unfinalized preview data
- Management screens at `/labor-cost/rates`, `/labor-cost/allowances`, and `/labor-cost/monthly`
- Wage and estimate information is restricted to `system_admin` and `shift_manager`
- Formal payroll finalization, payslips, tax/social insurance, statutory premium calculation, PDF/Excel, and external payroll/accounting integrations remain outside this phase

Phase 12 adds monthly labor cost budget and variance management:

- Monthly labor cost budgets with draft, review, approved, reopened, and archived states
- Planned labor cost preview from an active publication, confirmed plan, or draft plan, in that priority order
- Approval snapshots for daily plan records, staff summaries, daily summaries, and planned allowances
- Current comparison with Phase 11 actual labor cost estimates without changing approved planned-cost snapshots
- Budget variance, planned-versus-actual variance, consumption ratios, and explicit normal/warning/critical statuses
- Separate approval and comparison issues so changing actual estimates does not invalidate budget approval
- UTF-8 BOM CSV export from approved snapshots or unapproved live preview
- Management screen at `/labor-cost/budget` and budget context on `/labor-cost/monthly`
- Budget, planned cost, actual estimate, rates, and allowances remain restricted to `system_admin` and `shift_manager`
- Sales, labor-cost ratios, automatic shift optimization, and formal payroll remain outside this phase

Phase 13 adds monthly revenue performance management:

- Location-specific revenue categories and monthly revenue budget/actual lines
- Revenue budget approval and revenue actual finalization with warning acknowledgement and validation fingerprint checks
- Immutable monthly performance snapshots covering revenue variance, attainment, labor-cost ratios, and labor-cost variance
- Approved/finalized source priority with explicit live fallbacks and visible warnings
- UTF-8 BOM CSV exports for revenue budgets, actuals, and performance summaries
- Financial management screen at `/finance/performance` and revenue context on `/labor-cost/budget`
- All revenue, budget, labor-cost, and ratio information remains restricted to `system_admin` and `shift_manager`
- Formal accounting, tax, payroll, member-system integration, forecasting, PDF, and Excel remain outside this phase
