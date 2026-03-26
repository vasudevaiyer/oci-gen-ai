#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$ROOT_DIR/.runtime"
PID_FILE="$PID_DIR/rag_service.pid"
LOG_FILE="$PID_DIR/rag_service.log"
STARTUP_WAIT_SECONDS="${STARTUP_WAIT_SECONDS:-8}"
PORT="${RAG_SERVICE_PORT:-8045}"

mkdir -p "$PID_DIR"

is_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

current_pid() {
  if [[ -f "$PID_FILE" ]]; then
    tr -d '[:space:]' < "$PID_FILE"
  fi
}

listener_pids() {
  lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true
}

stop_pid() {
  local pid="$1"
  local label="$2"

  if [[ -z "$pid" ]] || ! is_running "$pid"; then
    return 0
  fi

  echo "Stopping $label (PID $pid)..."
  kill "$pid"

  for _ in {1..20}; do
    if ! is_running "$pid"; then
      return 0
    fi
    sleep 1
  done

  echo "$label did not stop gracefully. Sending SIGKILL..."
  kill -9 "$pid"
}

stop_existing() {
  local pid
  pid="$(current_pid)"

  if [[ -n "${pid:-}" ]]; then
    stop_pid "$pid" "service from PID file"
  fi

  while IFS= read -r listener_pid; do
    if [[ -z "$listener_pid" ]]; then
      continue
    fi
    if [[ -n "${pid:-}" && "$listener_pid" == "$pid" ]]; then
      continue
    fi
    stop_pid "$listener_pid" "listener on port $PORT"
  done < <(listener_pids)

  rm -f "$PID_FILE"
}

start_service() {
  echo "Starting service in background on port $PORT..."
  cd "$ROOT_DIR"

  set -a
  if [[ -f .env ]]; then
    source .env
  fi
  set +a

  export PYTHONPATH="$ROOT_DIR:${PYTHONPATH:-}"

  nohup /u01/venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port "$PORT" >"$LOG_FILE" 2>&1 < /dev/null &
  local pid=$!
  echo "$pid" > "$PID_FILE"

  for _ in $(seq 1 "$STARTUP_WAIT_SECONDS"); do
    if ! is_running "$pid"; then
      echo "Service exited during startup. Check $LOG_FILE" >&2
      rm -f "$PID_FILE"
      return 1
    fi

    if listener_pids | grep -qx "$pid" && curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
      echo "Service is up on port $PORT (PID $pid)."
      echo "Log: $LOG_FILE"
      return 0
    fi

    sleep 1
  done

  echo "Service did not become healthy on port $PORT in time. Check $LOG_FILE" >&2
  return 1
}

stop_existing
start_service
