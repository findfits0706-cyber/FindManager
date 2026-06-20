#!/usr/bin/env bash
set -euo pipefail
. .venv/bin/activate
cd backend
pytest
ruff check .
ruff format --check .
python manage.py makemigrations --check
python manage.py check
cd ../frontend
npm run lint
npm run typecheck
npm run test -- --run
npm run build
