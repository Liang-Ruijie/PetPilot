#!/usr/bin/env bash
set -euo pipefail
# verify.sh 调用的重启恢复检查钩子。契约：0=通过；不碰真实数据；不调真实模型。
# 固定步骤：起服务 → 写唯一标记记录 → 杀进程并确认退出 → 再起 → 按 ID 读回比对。

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
PORT=8010
DB="$BACKEND/data/restart-check.db"
export DATABASE_URL="sqlite:///$DB"
export MODEL_API_KEY=""

PID=""
cleanup() {
  if [ -n "$PID" ]; then
    kill "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true
  fi
  rm -f "$DB"
}
trap cleanup EXIT

start_service() {
  uvicorn app.main:app --host 127.0.0.1 --port "$PORT" &
  PID=$!
}

wait_ready() {
  for _ in $(seq 1 50); do
    if curl -s -X POST "http://127.0.0.1:$PORT/api/auth/login" \
        -H 'Content-Type: application/json' -d '{"code":"123456"}' >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.2
  done
  echo "服务未能就绪"
  return 1
}

cd "$BACKEND"

echo "1. 准备临时数据库（${DB}）"
rm -f "$DB"
source .venv/bin/activate
alembic upgrade head

MARK="restart-check-$(date +%s)"

echo "2. 起服务（端口 ${PORT}）"
start_service
wait_ready

echo "3. 登录并写入带唯一标记的猫"
TOKEN="$(curl -s -X POST "http://127.0.0.1:$PORT/api/auth/login" \
  -H 'Content-Type: application/json' -d '{"code":"123456"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')"
curl -s -X POST "http://127.0.0.1:$PORT/api/pets" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"name\":\"$MARK\"}" >/dev/null

echo "4. 杀掉服务并确认退出"
kill "$PID"
wait "$PID" 2>/dev/null || true
PID=""

echo "5. 再起服务，按名字读回比对"
start_service
wait_ready
TOKEN2="$(curl -s -X POST "http://127.0.0.1:$PORT/api/auth/login" \
  -H 'Content-Type: application/json' -d '{"code":"123456"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')"
FOUND="$(curl -s "http://127.0.0.1:$PORT/api/pets" -H "Authorization: Bearer $TOKEN2" \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print("yes" if any(p["name"]=="'"$MARK"'" for p in d["pets"]) else "no")')"

echo "6. 结果比对：$FOUND"
if [ "$FOUND" = "yes" ]; then
  echo "通过：重启后数据仍在"
  exit 0
else
  echo "不通过：重启后数据丢失"
  exit 1
fi
