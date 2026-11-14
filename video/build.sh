#!/usr/bin/env bash
# Turns the recorded frames into the demo video (1920x1080, 30 fps, H.264, silent).
# Run from the repo root, in Linux/WSL or anywhere ffmpeg is installed:  bash video/build.sh
set -euo pipefail
IN=${1:-video/out/frames}
OUT=${2:-video/out/trailmark-demo.mp4}
ffmpeg -loglevel error -y -framerate 30 -i "$IN/f%05d.jpg" \
  -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=48000 -shortest \
  -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -r 30 -movflags +faststart \
  -c:a aac -b:a 128k "$OUT"
ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "$OUT"
