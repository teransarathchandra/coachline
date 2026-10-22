#!/usr/bin/env bash
# The website's media, made from the README's: each GIF as an MP4 with a poster from late in the recording, each screenshot as WebP.
# Run from the repo root after re-recording (bash docs/demo/record-all.sh): bash docs/demo/web_media.sh
set -euo pipefail
cd "$(dirname "$0")/../../docs/assets"
command -v ffmpeg >/dev/null || { echo "missing: ffmpeg" >&2; exit 1; }
# WebP by ffmpeg where it has libwebp, else by cwebp (brew install webp): Homebrew's ffmpeg 9 has no WebP encoder
if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libwebp; then webp() { ffmpeg -hide_banner -loglevel error -y -i "$1" -c:v libwebp -quality 84 "$2"; }
else command -v cwebp >/dev/null || { echo "missing: a WebP encoder (brew install webp)" >&2; exit 1; }; webp() { cwebp -quiet -q 84 "$1" -o "$2"; }; fi
frame=$(mktemp -t poster).png
for g in prompt install website hint use library; do
  ffmpeg -hide_banner -loglevel error -y -i "$g.gif" -movflags +faststart -pix_fmt yuv420p -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" -c:v libx264 -crf 24 -preset slow "$g.mp4"
  d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$g.mp4")
  at=0.82; [ "$g" = hint ] && at=0.075       # the hint's words show after the first pause; by the end the meter is full and says no more
  ffmpeg -hide_banner -loglevel error -y -ss "$(python3 -c "print(round($d * $at, 2))")" -i "$g.mp4" -frames:v 1 "$frame"
  webp "$frame" "$g-poster.webp"
  echo "ok   $g.mp4, $g-poster.webp"
done
rm -f "$frame"
for s in screenshot screenshot-pane desktop editor; do
  if [ -f "$s.png" ]; then webp "$s.png" "$s.webp" && echo "ok   $s.webp"; fi
done
