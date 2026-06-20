$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
}
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\pip install -e .\backend[dev]
Set-Location .\frontend
npm install
