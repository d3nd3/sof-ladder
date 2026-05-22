#!/bin/bash
set -e
# shellcheck source=lib/common.sh
source "$(dirname "$0")/lib/common.sh"
require_venv
init_db_once

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8080}"

if [ "${1:-}" = "--fg" ] || [ "${1:-}" = "--foreground" ]; then
  exec "$UV" backend.main:app --host "$API_HOST" --port "$API_PORT" --reload
fi

start_bg api "$UV" backend.main:app --host "$API_HOST" --port "$API_PORT"
wait_for_api
