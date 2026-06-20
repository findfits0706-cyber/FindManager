$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
Set-Location .\backend
& ..\.venv\Scripts\python -m pytest
& ..\.venv\Scripts\python -m ruff check .
& ..\.venv\Scripts\python -m ruff format --check .
& ..\.venv\Scripts\python manage.py makemigrations --check
& ..\.venv\Scripts\python manage.py check
Set-Location ..\frontend
npm run lint
npm run typecheck
npm run test -- --run
npm run build
