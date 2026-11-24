"""Mixes the music bed and video/out/sfx.wav under the demo video and levels it to -16 LUFS.
Run where ffmpeg is installed (Linux/WSL): python3 video/mix.py -> video/out/trailmark-demo-sound.mp4"""
import os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
# music under the sound effects: fade in, fade out over the end card, then the whole mix to -16 LUFS
video = os.path.join(HERE, 'out', 'trailmark-demo.mp4'); out = os.path.join(HERE, 'out', 'trailmark-demo-sound.mp4')
vdur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', video], capture_output=True, text=True).stdout)
fo = max(0, vdur - 3.5)
subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', video, '-i', os.path.join(HERE, 'audio', 'bed.mp3'), '-i', os.path.join(HERE, 'out', 'sfx.wav'),
                '-filter_complex',
                f'[1:a]atrim=0:{vdur:.2f},afade=t=in:d=1.2,afade=t=out:st={fo:.2f}:d=3.5,volume=0.32[m];'
                f'[2:a]atrim=0:{vdur:.2f}[s];[m][s]amix=inputs=2:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]',
                '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-shortest', '-movflags', '+faststart', out], check=True)
print(out, f'{vdur:.1f} s')
