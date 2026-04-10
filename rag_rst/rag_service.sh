#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/.rag_service.pid"
LOG_DIR="$ROOT_DIR/logs"
LOG_FILE="$LOG_DIR/rag_service.log"
ENV_FILE="${RAG_ENV_FILE:-$ROOT_DIR/rag.env}"
FALLBACK_ENV_FILE="$ROOT_DIR/.env"
PYTHON_BIN="${RAG_PYTHON_BIN:-/u01/venv/bin/python}"
HOST="${RAG_HOST:-0.0.0.0}"
PORT="${RAG_PORT:-8000}"

required_env_vars=(
  ORACLE_USER
  ORACLE_PASSWORD
  ORACLE_DSN
  ORACLE_WALLET_DIR
  ORACLE_WALLET_PASSWORD
  OCI_CONFIG_PATH
  OCI_PROFILE
  OCI_COMPARTMENT_OCID
)

load_env() {
  local file_to_source=""
  if [[ -f "$ENV_FILE" ]]; then
    file_to_source="$ENV_FILE"
  elif [[ -f "$FALLBACK_ENV_FILE" ]]; then
    file_to_source="$FALLBACK_ENV_FILE"
  fi

  if [[ -n "$file_to_source" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$file_to_source"
    set +a
  fi
}

missing_env() {
  local missing=()
  local name
  for name in "${required_env_vars[@]}"; do
    if [[ -z "${!name:-}" ]]; then
      missing+=("$name")
    fi
  done

  if [[ "${#missing[@]}" -gt 0 ]]; then
    printf 'Missing required environment variables:\n' >&2
    printf '  %s\n' "${missing[@]}" >&2
    printf 'Create %s from rag.env.example or export them before starting.\n' "$ENV_FILE" >&2
    return 1
  fi
}

is_running() {
  if [[ ! -f "$PID_FILE" ]]; then
    return 1
  fi

  local pid
  pid="$(<"$PID_FILE")"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

start_service() {
  load_env
  missing_env

  if [[ ! -x "$PYTHON_BIN" ]]; then
    printf 'Python runtime not found at %s\n' "$PYTHON_BIN" >&2
    return 1
  fi

  if is_running; then
    printf 'RAG app is already running with PID %s\n' "$(<"$PID_FILE")"
    return 0
  fi

  mkdir -p "$LOG_DIR"

  if [[ ! -f "$ROOT_DIR/frontend/dist/index.html" ]]; then
    printf 'Warning: frontend/dist/index.html not found. The API will start, but the built UI will not be served.\n' >&2
  fi

  (
    cd "$ROOT_DIR"
    nohup "$PYTHON_BIN" -m uvicorn backend.app.main:app --host "$HOST" --port "$PORT" >>"$LOG_FILE" 2>&1 < /dev/null &
    echo $! > "$PID_FILE"
  )

  sleep 1
  if is_running; then
    printf 'RAG app started with PID %s\n' "$(<"$PID_FILE")"
    printf 'URL: http://%s:%s\n' "$HOST" "$PORT"
    printf 'Log: %s\n' "$LOG_FILE"
    return 0
  fi

  printf 'RAG app failed to start. Check %s\n' "$LOG_FILE" >&2
  return 1
}

stop_service() {
  if ! is_running; then
    rm -f "$PID_FILE"
    printf 'RAG app is not running\n'
    return 0
  fi

  local pid
  pid="$(<"$PID_FILE")"
  kill "$pid"

  for _ in {1..10}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$PID_FILE"
      printf 'RAG app stopped\n'
      return 0
    fi
    sleep 1
  done

  printf 'Process %s did not stop after 10s\n' "$pid" >&2
  return 1
}

status_service() {
  if is_running; then
    printf 'RAG app is running with PID %s\n' "$(<"$PID_FILE")"
    printf 'URL: http://%s:%s\n' "$HOST" "$PORT"
    printf 'Log: %s\n' "$LOG_FILE"
    return 0
  fi

  printf 'RAG app is not running\n'
  return 1
}

case "${1:-start}" in
  start)
    start_service
    ;;
  stop)
    stop_service
    ;;
  restart)
    stop_service || true
    start_service
    ;;
  status)
    load_env
    status_service
    ;;
  *)
    printf 'Usage: %s {start|stop|restart|status}\n' "$(basename "$0")" >&2
    exit 1
    ;;
esac
