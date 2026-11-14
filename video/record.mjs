// Records video/stage.html as one continuous take, in real time, with Chrome's screencast.
// Each frame is saved with its timestamp; video/build.py turns them into a constant 30 fps video.
// Needs the repo served on 127.0.0.1:8765 (`python -m trailmark view --no-browser`).
// Usage: node video/record.mjs [outDir]
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';

const OUT = resolve(process.argv[2] || 'video/out/frames');
rmSync(OUT, { recursive: true, force: true }); mkdirSync(OUT, { recursive: true });
const PORT = 9712;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const chrome = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${join(tmpdir(), 'trailmark-rec-' + Date.now())}`,
  '--window-size=1920,1080', '--hide-scrollbars', '--force-color-profile=srgb', '--mute-audio',
  '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows',
  'about:blank'], { stdio: 'ignore' });

let target;
for (let i = 0; i < 80 && !target; i++) { try { target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: 'PUT' })).json(); } catch { await sleep(250); } }
if (!target) throw new Error('Chrome did not start');
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r, { once: true }));
let seq = 0; let recording = false; const pending = new Map(); const frames = [];
const send = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); return; }
  if (m.method === 'Page.screencastFrame') {
    const { data, metadata, sessionId } = m.params;
    if (recording) {
      const name = `f${String(frames.length).padStart(5, '0')}.jpg`;
      writeFileSync(join(OUT, name), Buffer.from(data, 'base64'));
      frames.push({ file: name, t: metadata.timestamp });
    }
    send('Page.screencastFrameAck', { sessionId });
  }
});
const evaluate = async (expr) => (await send('Runtime.evaluate', { expression: expr, returnByValue: true })).result.value;

await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: 'http://127.0.0.1:8765/video/stage.html' });
for (let i = 0; i < 240; i++) { if (await evaluate('window.stageReady === true').catch(() => false)) break; await sleep(250); }
if (!(await evaluate('window.stageReady === true'))) throw new Error('stage never became ready');
console.log('stage ready, recording');

await send('Page.startScreencast', { format: 'jpeg', quality: 90, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });
await sleep(500);
recording = true;
await evaluate('window.startTimeline(); 1');
const t0 = Date.now();
for (;;) { await sleep(1000); if (await evaluate('window.timelineDone === true')) break; if (Date.now() - t0 > 170000) { console.log('timeout'); break; } }
await sleep(400);
recording = false;
await send('Page.stopScreencast');
writeFileSync(join(OUT, 'frames.json'), JSON.stringify(frames));
const dur = frames.at(-1).t - frames[0].t;
console.log(`${frames.length} frames over ${dur.toFixed(1)} s (${(frames.length / dur).toFixed(1)} fps) -> ${OUT}`);
chrome.kill();
process.exit(0);
