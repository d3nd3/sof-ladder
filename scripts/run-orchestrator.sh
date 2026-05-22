#!/bin/bash
set -e
# shellcheck source=lib/common.sh
source "$(dirname "$0")/lib/common.sh"
require_venv

if [ "${1:-}" = "--fg" ] || [ "${1:-}" = "--foreground" ]; then
  exec "$PY" -m orchestrator.main
fi

start_bg orchestrator "$PY" -m orchestrator.main
