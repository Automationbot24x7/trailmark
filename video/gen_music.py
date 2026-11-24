"""Generates the instrumental bed for the demo video (ElevenLabs Music through SandBase credits).
Usage: python gen_music.py <name> <seconds> "<prompt>"  -> video/audio/<name>.mp3"""
import sys, pathlib
sys.path.insert(0, r"C:\Hackathon\chroma\tools")
import sb
name, seconds, prompt = sys.argv[1], float(sys.argv[2]), sys.argv[3]
out = pathlib.Path(__file__).parent / "audio"
d = sb.run("elevenlabs/music/2.5", {"prompt": prompt, "music_length_ms": int(seconds * 1000), "force_instrumental": True}, out / f"{name}.json")
outs = d.get("outputs") or d.get("output") or []
url = (outs[0]["url"] if isinstance(outs[0], dict) else outs[0]) if isinstance(outs, list) and outs else (outs if isinstance(outs, str) else None)
print(d.get("status"), bool(url), (d.get("error") or "")[:200])
if url: sb.download(url, out / f"{name}.mp3"); print("saved", out / f"{name}.mp3")
