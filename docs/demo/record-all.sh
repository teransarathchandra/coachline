#!/usr/bin/env bash
# Records the README / website recordings on a Mac, in order, from the repo root:  bash docs/demo/record-all.sh [name ...]
# The other GIFs need no recording: python3 docs/demo/scene_gifs.py makes them from the website (see docs/demo/HANDOFF.md).
# Needs vhs (brew install vhs), ffmpeg, python3 with Pillow (pip3 install pillow), and the demo login signed in once:
#   CLAUDE_CONFIG_DIR=~/.claude-coachline-demo claude auth login
# With names (install prompt website), records only those. Each take is checked: the file must exist and be newer than the start
# of its run. They use the demo login's subscription. website is taken for the hero still, docs/assets/screenshot.png.
set -euo pipefail
cd "$(dirname "$0")/../.."
for t in vhs ffmpeg python3; do command -v "$t" >/dev/null || { echo "missing: $t" >&2; exit 1; }; done
python3 -c "import PIL" 2>/dev/null || { echo "missing: Pillow (pip3 install pillow)" >&2; exit 1; }
[ -d "$HOME/.claude-coachline-demo" ] || { echo "sign in to the demo login first: CLAUDE_CONFIG_DIR=~/.claude-coachline-demo claude auth login" >&2; exit 1; }
mkdir -p docs/demo/.rec

ALL=(install prompt website)
NAMES=("${@:-${ALL[@]}}")
for n in "${NAMES[@]}"; do
  start=$(date +%s); echo "== $n"
  vhs "docs/demo/$n.tape"
  if [ -f "docs/demo/$n.zoom.json" ]; then python3 docs/demo/zoom.py "docs/demo/$n.zoom.json"; fi
  out="docs/assets/$n.gif"
  if [ ! -f "$out" ] || [ "$(stat -f %m "$out")" -lt "$start" ]; then echo "FAILED: $out was not written" >&2; exit 1; fi
  echo "ok   $out ($(du -h "$out" | cut -f1))"
done
echo "done. Check each GIF by eye, then: git status docs/assets"
