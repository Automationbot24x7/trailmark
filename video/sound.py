"""Builds the sound track for the demo video: the instrumental bed plus soft UI sounds placed at the
moments the take logged (video/out/frames/events.json, wall-clock seconds matched to the frame times).
Sounds are synthesised here; nothing is sampled. Usage (WSL, needs numpy + ffmpeg):
  python video/sound.py (needs numpy) -> video/out/sfx.wav; then video/mix.py (needs ffmpeg) mixes it with the music"""
import json, os, subprocess, wave
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(HERE, 'out', 'frames')
frames = json.load(open(os.path.join(FR, 'frames.json')))
events = json.load(open(os.path.join(FR, 'events.json')))
T0 = frames[0]['t']
SR = 48000
DUR = frames[-1]['t'] - T0 + 5.0 + 0.5
N = int(DUR * SR)
L = np.zeros(N); R = np.zeros(N)
rng = np.random.default_rng(11)


def put(sig, t, g=1.0, pan=0.5):
    a = int(t * SR)
    if a < 0 or a >= N: return
    b = min(N, a + len(sig)); sig = sig[:b - a]
    L[a:b] += sig * g * np.sqrt(2 * (1 - pan)); R[a:b] += sig * g * np.sqrt(2 * pan)


def env_ad(n, attack=0.002, decay=8.0):
    t = np.arange(n) / SR
    return (1 - np.exp(-t / attack)) * np.exp(-t * decay)


def bell(f, d=1.2, decay=4.0):
    n = int(d * SR); t = np.arange(n) / SR
    s = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2.01 * f * t) + 0.12 * np.sin(2 * np.pi * 3.02 * f * t)
    return s * env_ad(n, 0.003, decay)


def band_noise(d, lo, hi, decay):
    n = int(d * SR); x = rng.normal(0, 1, n)
    X = np.fft.rfft(x); f = np.fft.rfftfreq(n, 1 / SR); X[(f < lo) | (f > hi)] = 0
    y = np.fft.irfft(X, n); y /= np.max(np.abs(y)) + 1e-9
    return y * env_ad(n, 0.0008, decay)


def tick(f=2400, d=0.03):
    n = int(d * SR); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * f * t) * 0.5 + band_noise(d, 1500, 7000, 120) * 0.5) * env_ad(n, 0.0005, 140)


def pop(f0, f1, d=0.14):
    n = int(d * SR); t = np.arange(n) / SR
    f = f0 * (f1 / f0) ** (t / d); ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * env_ad(n, 0.002, 26)


def whoosh(d=0.9):
    n = int(d * SR); x = rng.normal(0, 1, n); t = np.arange(n) / SR
    X = np.fft.rfft(x); f = np.fft.rfftfreq(n, 1 / SR); X[(f < 250) | (f > 4500)] = 0
    y = np.fft.irfft(X, n); y /= np.max(np.abs(y)) + 1e-9
    return y * np.sin(np.pi * t / d) ** 2


def soft(sig, cutoff=4500, room=0.18):
    n = len(sig) + int(0.7 * SR)
    X = np.fft.rfft(np.pad(sig, (0, n - len(sig)))); f = np.fft.rfftfreq(n, 1 / SR)
    X *= 1 / np.sqrt(1 + (f / cutoff) ** 4)
    y = np.fft.irfft(X, n)
    ir = rng.normal(0, 1, int(0.7 * SR)) * np.exp(-np.arange(int(0.7 * SR)) / SR * 7); ir /= np.sqrt(np.sum(ir ** 2))
    wet = np.convolve(y, ir)[:n]
    return y + room * wet


at = lambda e: e['w'] - T0
for e in events:
    k, t = e['k'], at(e)
    if k == 'intro':          # the logo's dots pop in, then the open circle and its ring (timings from the CSS)
        for dt, f in ((0.1, 520), (0.45, 620), (0.8, 740)): put(pop(f * 0.8, f), t + dt, 0.22)
        put(pop(700, 990), t + 1.15, 0.2, 0.6); put(bell(1318, 1.4, 3.2), t + 1.3, 0.07, 0.6)
    elif k == 'click': put(tick(), t, 0.22, 0.55)
    elif k == 'snip':         # scissors: two bright snips and a soft thud
        put(soft(band_noise(0.05, 2500, 9000, 70)), t + 0.02, 0.2, 0.5); put(soft(band_noise(0.05, 2800, 10000, 70)), t + 0.11, 0.17, 0.5)
        put(pop(180, 90, 0.25), t + 0.12, 0.14)
    elif k == 'alert':        # caught: a low two-note fall
        put(soft(bell(659.3, 1.6, 2.8)), t, 0.11, 0.45); put(soft(bell(523.3, 2.0, 2.2)), t + 0.16, 0.11, 0.55)
    elif k == 'ok':           # fixed: a bright two-note rise
        put(soft(bell(784.0, 1.4, 3.0)), t + 0.1, 0.09, 0.45); put(soft(bell(1174.7, 1.8, 2.6)), t + 0.24, 0.09, 0.55)
    elif k == 'whoosh': pass  # removed after the sound review: read as hiss
    elif k == 'end': put(bell(587.3, 2.6, 1.6), t + 0.2, 0.1, 0.45); put(bell(880.0, 2.6, 1.6), t + 0.32, 0.08, 0.55)
# typing: soft key ticks between each typeStart and typeEnd
starts = [at(e) for e in events if e['k'] == 'typeStart']; ends = [at(e) for e in events if e['k'] == 'typeEnd']
for a, b in zip(starts, ends):
    t = a
    while t < b:
        put(soft(tick(rng.uniform(900, 1500), 0.02), 2800, 0.05), t, rng.uniform(0.03, 0.05), rng.uniform(0.4, 0.6)); t += rng.uniform(0.11, 0.2)

sfx = np.stack([L, R], 1)
with wave.open(os.path.join(HERE, 'out', 'sfx.wav'), 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(sfx, -1, 1) * 32767).astype('<i2').tobytes())

print('wrote', os.path.join(HERE, 'out', 'sfx.wav'), len(events), 'events')
