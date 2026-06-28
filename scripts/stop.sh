#!/bin/bash
# Stop the VALENCE dev API if running.
set -euo pipefail

cd "$(dirname "$0")/.."

VALENCE_PORT="${VALENCE_PORT:-8000}"
PID_FILE="${VALENCE_PID_FILE:-$(pwd)/.valence-api.pid}"

stopped=0

if [ -f "$PID_FILE" ]; then
  pid=$(cat "$PID_FILE" 2>/dev/null || true)
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "Stopping VALENCE API (PID $pid)..."
    kill -TERM "$pid" 2>/dev/null || true
    sleep 1
    kill -9 "$pid" 2>/dev/null || true
    stopped=1
  fi
  rm -f "$PID_FILE"
fi

if command -v lsof >/dev/null 2>&1; then
  for pid in $(lsof -t -iTCP:"$VALENCE_PORT" -sTCP:LISTEN 2>/dev/null || true); do
  cmd=$(ps -p "$pid" -o args= 2>/dev/null || true)
  if [[ "$cmd" == *"valence-api"* ]] || [[ "$cmd" == *"grc_dashboard.api.main"* ]]; then
    echo "Stopping VALENCE on port $VALENCE_PORT (PID $pid)..."
    kill -TERM "$pid" 2>/dev/null || true
    sleep 0.5
    kill -9 "$pid" 2>/dev/null || true
    stopped=1
  fi
  done
fi

if [ "$stopped" -eq 1 ]; then
  echo "VALENCE API stopped."
else
  echo "No VALENCE API process found on port $VALENCE_PORT."
fi
