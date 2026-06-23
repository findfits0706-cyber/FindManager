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
