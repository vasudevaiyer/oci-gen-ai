#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

source /u01/venv/bin/activate
export PYTHONPATH="$ROOT_DIR:${PYTHONPATH:-}"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

exec /u01/venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8045
