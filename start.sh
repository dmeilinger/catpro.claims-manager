#!/bin/bash
ROOT="$(cd "$(dirname "$0")" && pwd)"

cd "$ROOT/backend" && "$ROOT/.venv/bin/uvicorn" app.main:app --reload --host 127.0.0.1 --port 8175 &
echo $! > "$ROOT/.backend.pid"

cd "$ROOT/frontend" && npm run dev &
echo $! > "$ROOT/.frontend.pid"

echo "Started. Backend PID $(cat "$ROOT/.backend.pid"), Frontend PID $(cat "$ROOT/.frontend.pid")"
