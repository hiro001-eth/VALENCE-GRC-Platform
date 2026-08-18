#!/bin/bash
# VALENCE GRC — dev server launcher with safe port reuse.
set -euo pipefail

cd "$(dirname "$0")"

VALENCE_PORT="${VALENCE_PORT:-8000}"
VALENCE_HOST="${VALENCE_HOST:-0.0.0.0}"
PID_FILE="${VALENCE_PID_FILE:-$(pwd)/.valence-api.pid}"
export VALENCE_PORT VALENCE_HOST VALENCE_PID_FILE="$PID_FILE"

is_valence_pid() {
  local pid="$1"
  local cmd
  cmd=$(ps -p "$pid" -o args= 2>/dev/null || true)
  if [[ "$cmd" == *"valence-api"* ]] || [[ "$cmd" == *"grc_dashboard.api.main"* ]]; then
    return 0
  fi

  # Uvicorn reload workers can inherit the listening socket but appear as
  # generic multiprocessing children. Walk the parent chain so we still
  # recognize them as part of this app before deciding the port is foreign.
  local parent
  parent=$(ps -p "$pid" -o ppid= 2>/dev/null | tr -d '[:space:]')
  while [[ -n "$parent" && "$parent" != "0" && "$parent" != "1" ]]; do
    cmd=$(ps -p "$parent" -o args= 2>/dev/null || true)
    if [[ "$cmd" == *"valence-api"* ]] || [[ "$cmd" == *"grc_dashboard.api.main"* ]]; then
      return 0
    fi
    parent=$(ps -p "$parent" -o ppid= 2>/dev/null | tr -d '[:space:]')
  done

  return 1
}

port_listener_pids() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -iTCP:"$VALENCE_PORT" -sTCP:LISTEN 2>/dev/null || true
    return
  fi
  if command -v ss >/dev/null 2>&1; then
    ss -tlnp 2>/dev/null | grep ":${VALENCE_PORT} " | grep -oP 'pid=\K[0-9]+' || true
    return
  fi
  if command -v fuser >/dev/null 2>&1; then
    fuser -n tcp "$VALENCE_PORT" 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+$' || true
  fi
}

stop_pid_gracefully() {
  local pid="$1"
  kill -TERM "$pid" 2>/dev/null || return 0
  local i
  for i in $(seq 1 15); do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 0.2
  done
  kill -9 "$pid" 2>/dev/null || true
}

ensure_port_available() {
  # Stop process recorded in our PID file (may be stale).
  if [ -f "$PID_FILE" ]; then
    local recorded
    recorded=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$recorded" ] && kill -0 "$recorded" 2>/dev/null && is_valence_pid "$recorded"; then
      echo "Stopping previous VALENCE API (PID $recorded)..."
      stop_pid_gracefully "$recorded"
    fi
    rm -f "$PID_FILE"
  fi

  # Free port from any other VALENCE instance; fail if a foreign process holds it.
  local listeners
  listeners="$(port_listener_pids)"

  local pid
  for pid in $listeners; do
    [ -n "$pid" ] || continue
    if ! is_valence_pid "$pid"; then
      local cmd
      cmd=$(ps -p "$pid" -o args= 2>/dev/null || echo "unknown")
      echo "ERROR: Port $VALENCE_PORT is already in use by another program (PID $pid):"
      echo "  $cmd"
      echo ""
      echo "Stop that process first, or use a different port:"
      echo "  VALENCE_PORT=8001 ./run.sh"
      exit 1
    fi
  done

  for pid in $listeners; do
    [ -n "$pid" ] || continue
    echo "Freeing port $VALENCE_PORT (stopping stale VALENCE PID $pid)..."
    stop_pid_gracefully "$pid"
  done

  local i
  for i in $(seq 1 25); do
    [ -z "$(port_listener_pids)" ] && return 0
    sleep 0.2
  done

  echo "ERROR: Port $VALENCE_PORT is still in use after cleanup."
  exit 1
}

echo "Starting VALENCE GRC Dashboard on http://${VALENCE_HOST}:${VALENCE_PORT} ..."

# Keep the installed package in sync with source.
if command -v uv >/dev/null 2>&1; then
  uv pip install -e . -q
elif [ -f "./.venv/bin/python" ]; then
  ./.venv/bin/python -m pip install -e . -q 2>/dev/null || true
fi

if [ ! -f "./.venv/bin/valence-api" ]; then
  echo "Virtual environment not found or valence-api not installed."
  echo "Run: ./scripts/setup_dev.sh"
  exit 1
fi

export VALENCE_RELOAD="${VALENCE_RELOAD:-true}"
ensure_port_available
exec ./.venv/bin/valence-api
