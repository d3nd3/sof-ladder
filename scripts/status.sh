#!/bin/bash
# shellcheck source=lib/common.sh
source "$(dirname "$0")/lib/common.sh"

for name in api bot orchestrator; do
  pidfile="$RUN_DIR/$name.pid"
  if is_running "$pidfile"; then
    echo "$name: running pid $(cat "$pidfile")"
  else
    echo "$name: stopped"
  fi
done

if curl -sf "${API_BASE:-http://127.0.0.1:8080}/health" >/dev/null 2>&1; then
  echo "api health: ok (${API_BASE:-http://127.0.0.1:8080})"
else
  echo "api health: unreachable"
fi

if [ -x "$PY" ]; then
  echo "--- resolved SoF paths ---"
  "$PY" -m ladder.sof_paths 2>/dev/null | sed 's/^/  /'
fi
