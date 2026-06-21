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

## Quality Gates

- Backend: `ruff`, `pytest`, `manage.py check`, `makemigrations --check`
- Frontend: `eslint`, `tsc --noEmit`, `vitest --run`, `vite build`
