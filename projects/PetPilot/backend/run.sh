#!/usr/bin/env bash
set -euo pipefail
# PetPilot 一条命令起服务（本机开发/演示）
cd "$(dirname "$0")"
source .venv/bin/activate
alembic upgrade head
exec uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8001}"
