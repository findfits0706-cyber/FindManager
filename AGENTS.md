# FindManager AGENTS

## Architecture

- Backend uses Django 5.2 with Django REST Framework.
- Frontend uses React 19 with Vite.
- Authentication is session-based with CSRF protection.
- All application APIs are versioned under `/api/v1/`.

## Conventions

- Use UUID primary keys.
- Use `Asia/Tokyo` as the default timezone.
- Never hard-delete staff or operational master records.
- Use action endpoints such as `deactivate` and `reactivate` instead of patching `is_active`.
- Keep migrations explicit and committed together with model changes.
- Validate with backend and frontend checks before handoff.

## Operational Domains

- `accounts`: staff accounts, roles, password lifecycle, audit history
- `common`: health check, pagination, audit events
- `operations`: locations, work definitions, staff assignments, staff capabilities

## Verification Commands

- Backend:
  - `ruff check .`
  - `ruff format --check .`
  - `pytest`
  - `python manage.py makemigrations --check`
  - `python manage.py check`
- Frontend:
  - `npm run lint`
  - `npm run typecheck`
  - `npm run test -- --run`
  - `npm run build`
