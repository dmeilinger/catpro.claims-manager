#!/bin/bash
ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$ROOT/logs"

cd "$ROOT/backend" && "$ROOT/.venv/bin/uvicorn" app.main:app --reload --host 127.0.0.1 --port 8175 >> "$ROOT/logs/uvicorn.log" 2>&1 &
echo $! > "$ROOT/.backend.pid"

cd "$ROOT/frontend" && npm run dev > "$ROOT/logs/vite.log" 2>&1 &
echo $! > "$ROOT/.frontend.pid"

echo "Started. Backend PID $(cat "$ROOT/.backend.pid"), Frontend PID $(cat "$ROOT/.frontend.pid")"
echo "Logs: logs/uvicorn.log, logs/vite.log, logs/poller.log"
