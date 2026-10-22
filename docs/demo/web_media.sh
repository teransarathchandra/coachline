#!/usr/bin/env bash
# The website's media, made from the README's: each GIF as an MP4 with a poster from late in the recording, each screenshot as WebP.
# Run from the repo root after re-recording (bash docs/demo/record-all.sh): bash docs/demo/web_media.sh
set -euo pipefail
cd "$(dirname "$0")/../../docs/assets"
command -v ffmpeg >/dev/null || { echo "missing: ffmpeg" >&2; exit 1; }
for g in prompt install website; do
  ffmpeg -hide_banner -loglevel error -y -i "$g.gif" -movflags +faststart -pix_fmt yuv420p -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" -c:v libx264 -crf 24 -preset slow "$g.mp4"
  d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$g.mp4")
  ffmpeg -hide_banner -loglevel error -y -ss "$(python3 -c "print(round($d * 0.82, 2))")" -i "$g.mp4" -frames:v 1 -c:v libwebp -quality 84 "$g-poster.webp"
  echo "ok   $g.mp4, $g-poster.webp"
done
for s in screenshot screenshot-pane desktop editor; do
  [ -f "$s.png" ] && ffmpeg -hide_banner -loglevel error -y -i "$s.png" -c:v libwebp -quality 84 "$s.webp" && echo "ok   $s.webp"
done
