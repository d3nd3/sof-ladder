#!/usr/bin/env bash
# Render docs/system.d2 -> docs/system.svg and verify it still reads cleanly.
# Usage: scripts/render-diagram.sh [path/to/system.d2]
set -euo pipefail

cd "$(dirname "$0")/.."
src="${1:-docs/system.d2}"
out="${src%.d2}.svg"

need_d2() {
  command -v d2 >/dev/null 2>&1 && return
  echo "d2 not found — install: https://d2lang.com (and the TALA plugin: 'd2 layout')" >&2
  exit 1
}
need_d2

# TALA gives the clean orthogonal routing this diagram relies on; fall back to
# ELK when the plugin isn't installed so CI/dev boxes without it don't break.
layout=tala
d2 layout 2>/dev/null | grep -q '^ *tala ' || layout=elk

d2 --layout="$layout" --theme=0 --dark-theme=200 "$src" "$out"
echo "rendered $out (layout: $layout)"
