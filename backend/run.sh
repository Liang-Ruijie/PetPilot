#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
.venv/bin/python -m alembic upgrade head
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8001}"
