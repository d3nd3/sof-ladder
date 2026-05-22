#!/bin/bash
# Copy ladder configs into a SoF server user directory
set -e
SOF_USER="${1:-/opt/sof/user}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cp "$ROOT/game/ladder_match.cfg" "$SOF_USER/"
mkdir -p "$SOF_USER/sofplus/sv" "$SOF_USER/sofplus/data/ladder_out"
cp "$ROOT/game/sofplus/"*.cfg "$SOF_USER/sofplus/sv/"
echo "Installed to $SOF_USER"
