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

## Phase 3 Domain Rules

- Shift patterns define a reusable one-day work sequence for one staff member.
- Weekly shift templates assign active shift patterns to staff by weekday, Monday through Sunday.
- Segment times are stored as offset minutes from midnight, not as `time` fields, so next-day work can be represented without introducing dated monthly shifts.
- Segment offsets must be in 15-minute increments and each active pattern must have at least one active segment.
- Removed segments and weekly entries are soft-deactivated rather than physically deleted.
- StaffCapability is not required when saving weekly templates because templates do not have concrete dates. Phase 4 validates dated StaffLocation and StaffCapability records when templates are expanded into monthly shifts.

## Quality Gates

- Backend: `ruff`, `pytest`, `manage.py check`, `makemigrations --check`
- Frontend: `eslint`, `tsc --noEmit`, `vitest --run`, `vite build`
