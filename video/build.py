#!/usr/bin/env python3
"""Builds the demo video from the recorded frames (video/out/frames + frames.json).
Each frame is held until the next one arrived, then the result is resampled to a constant 30 fps.
Run where ffmpeg is installed (Linux/WSL):  python3 video/build.py
Out: video/out/trailmark-demo.mp4 (1920x1080, 30 fps, H.264, silent AAC track for upload sites)
"""
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(HERE, 'out', 'frames')
OUT = os.path.join(HERE, 'out', 'trailmark-demo.mp4')
frames = json.load(open(os.path.join(FR, 'frames.json')))
lst = os.path.join(HERE, 'out', 'frames.txt')
with open(lst, 'w') as f:
    for a, b in zip(frames, frames[1:]):
        f.write(f"file '{os.path.join(FR, a['file'])}'\nduration {b['t'] - a['t']:.4f}\n")
    f.write(f"file '{os.path.join(FR, frames[-1]['file'])}'\nduration 5.0\n")  # the end card: nothing moves, so the screencast sent no more frames
    f.write(f"file '{os.path.join(FR, frames[-1]['file'])}'\n")
subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst,
                '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000',
                '-vf', 'fps=30,format=yuv420p', '-c:v', 'libx264', '-preset', 'slow', '-crf', '18',
                '-c:a', 'aac', '-b:a', '96k', '-shortest', '-movflags', '+faststart', OUT], check=True)
dur = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', OUT],
                     capture_output=True, text=True).stdout.strip()
print(f'{OUT}  {float(dur):.1f} s  {os.path.getsize(OUT) / 1e6:.1f} MB')
