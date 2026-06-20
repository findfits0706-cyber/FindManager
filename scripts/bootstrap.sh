#!/usr/bin/env bash
set -euo pipefail
cp -n .env.example .env || true
python -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -e ./backend[dev]
cd frontend
npm install
