#!/bin/bash
# Copy ladder configs into USER_SUBFOLDER under the SoF install
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/.env"
  set +a
fi
SOF_INSTALL_DIR="${SOF_INSTALL_DIR:-/opt/sof}"
SOF_USER_SUBFOLDER="${SOF_USER_SUBFOLDER:-user}"
SOF_CWD="${SOF_CWD:-$SOF_INSTALL_DIR}"
USER_DIR="${SOF_USER_DIR:-$SOF_CWD/$SOF_USER_SUBFOLDER}"
ADDONS="$USER_DIR/sofplus/addons"

cp "$ROOT/game/ladder_match.cfg" "$ROOT/game/ladder_hub.cfg" "$ROOT/game/ladder_verify.cfg" "$USER_DIR/"
mkdir -p "$ADDONS" "$USER_DIR/sofplus/data/ladder_out"
for f in "$ROOT/game/sofplus/addons/"*; do
  [ -f "$f" ] && cp "$f" "$ADDONS/"
done
echo "SOF_USER_SUBFOLDER=$SOF_USER_SUBFOLDER"
echo "user_dir=$USER_DIR"
echo "addons=$ADDONS"
