#!/bin/bash
# Start API → wait for health → bot → orchestrator (background)
set -e
DIR="$(dirname "$0")"

echo "=== SoF Ladder: starting services ==="
"$DIR/stop-all.sh" 2>/dev/null || true

"$DIR/run-api.sh"
"$DIR/run-bot.sh"
"$DIR/run-orchestrator.sh"

echo ""
echo "=== running ==="
"$DIR/status.sh"
echo ""
echo "Logs: .run/logs/   Stop: ./scripts/stop-all.sh"
echo "Foreground: ./scripts/run-api.sh --fg  (separate terminals for bot/orch)"
