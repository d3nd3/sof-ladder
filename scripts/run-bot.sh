#!/bin/bash
set -e
# shellcheck source=lib/common.sh
source "$(dirname "$0")/lib/common.sh"
require_venv

if [ -z "${DISCORD_BOT_TOKEN:-}" ]; then
  echo "DISCORD_BOT_TOKEN not set in .env" >&2
  exit 1
fi

if [ "${1:-}" = "--fg" ] || [ "${1:-}" = "--foreground" ]; then
  exec "$PY" -m bot.main
fi

start_bg bot "$PY" -m bot.main
