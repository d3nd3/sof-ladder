# Shared helpers for sof-ladder launch scripts
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/.env"
  set +a
fi

export PYTHONPATH="$ROOT"
RUN_DIR="$ROOT/.run"
LOG_DIR="$RUN_DIR/logs"
mkdir -p "$LOG_DIR"

PY="$ROOT/venv/bin/python"
UV="$ROOT/venv/bin/uvicorn"

require_venv() {
  if [ ! -x "$PY" ]; then
    echo "Missing venv. Run: python3 -m venv venv && ./venv/bin/pip install -r requirements.txt" >&2
    exit 1
  fi
}

init_db_once() {
  "$PY" -c "from ladder.db import init_db; init_db()"
}

wait_for_api() {
  local url="${API_BASE:-http://127.0.0.1:8080}"
  url="${url%/}/health"
  for _ in $(seq 1 40); do
    if curl -sf "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  echo "API not healthy at $url" >&2
  return 1
}

is_running() {
  local pidfile="$1"
  [ -f "$pidfile" ] || return 1
  local pid
  pid=$(cat "$pidfile")
  kill -0 "$pid" 2>/dev/null
}

start_bg() {
  local name="$1"
  shift
  local pidfile="$RUN_DIR/$name.pid"
  local logfile="$LOG_DIR/$name.log"
  if is_running "$pidfile"; then
    echo "$name already running (pid $(cat "$pidfile"))"
    return 0
  fi
  nohup "$@" >>"$logfile" 2>&1 &
  echo $! >"$pidfile"
  echo "started $name pid $(cat "$pidfile") log $logfile"
}

stop_one() {
  local name="$1"
  local pidfile="$RUN_DIR/$name.pid"
  if ! is_running "$pidfile"; then
    rm -f "$pidfile"
    return 0
  fi
  kill "$(cat "$pidfile")" 2>/dev/null
  rm -f "$pidfile"
  echo "stopped $name"
}
