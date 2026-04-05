#!/bin/bash
ROOT="$(cd "$(dirname "$0")" && pwd)"

for name in backend frontend; do
  pidfile="$ROOT/.$name.pid"
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile")
    kill "$pid" 2>/dev/null && echo "Stopped $name (PID $pid)" || echo "$name not running"
    rm "$pidfile"
  else
    echo "No PID file for $name"
  fi
done
