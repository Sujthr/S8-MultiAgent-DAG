#!/usr/bin/env bash
# stop.sh — stop the gateway
HERE="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$HERE/.gateway_pid"

echo "[stop] Stopping LLM Gateway V8..."

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    kill "$PID" 2>/dev/null && echo "[stop] Killed PID $PID" || echo "[stop] PID $PID not running"
    rm -f "$PID_FILE"
fi

# Also kill by port
PIDS=$(lsof -ti:8108 2>/dev/null || true)
if [ -n "$PIDS" ]; then
    echo "[stop] Killing processes on port 8108: $PIDS"
    kill -9 $PIDS 2>/dev/null || true
fi

echo "[stop] Done."
