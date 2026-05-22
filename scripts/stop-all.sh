#!/bin/bash
# shellcheck source=lib/common.sh
source "$(dirname "$0")/lib/common.sh"

stop_one orchestrator
stop_one bot
stop_one api
echo "all stopped"
