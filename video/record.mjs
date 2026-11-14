// Records video/stage.html as one continuous take: Chrome's virtual time is advanced one
// frame (1/30 s) at a time and every frame is captured, so the result is smooth however slow the machine.
// Needs `python -m trailmark view --no-browser` running (serves the repo on 127.0.0.1:8765).
// Usage: node video/record.mjs [outDir]   then build with video/build.sh (ffmpeg)
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';

const OUT = resolve(process.argv[2] || 'video/out/frames');
rmSync(OUT, { recursive: true, force: true }); mkdirSync(OUT, { recursive: true });
const PORT = 9711, FPS = 30;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const chrome = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${join(tmpdir(), 'trailmark-rec')}`,
  '--window-size=1920,1080', '--hide-scrollbars', '--force-color-profile=srgb', '--mute-audio', 'about:blank'], { stdio: 'ignore' });

let target;
for (let i = 0; i < 80 && !target; i++) { try { target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: 'PUT' })).json(); } catch { await sleep(250); } }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r, { once: true }));
let seq = 0; const pending = new Map(); const waiters = [];
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); return; }
  for (let i = waiters.length - 1; i >= 0; i--) if (waiters[i].name === m.method) { waiters[i].res(m.params); waiters.splice(i, 1); }
});
const send = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
const once = (name) => new Promise((res) => waiters.push({ name, res }));
const evaluate = async (expr) => (await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: false })).result.value;

await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: 'http://127.0.0.1:8765/video/stage.html' });
for (let i = 0; i < 240; i++) { if (await evaluate('window.stageReady === true').catch(() => false)) break; await sleep(250); }
if (!(await evaluate('window.stageReady === true'))) throw new Error('stage never became ready');
console.log('stage ready, recording');

await send('Emulation.setVirtualTimePolicy', { policy: 'pause' });
await evaluate('window.startTimeline(); 1');
let n = 0;
for (;;) {
  const expired = once('Emulation.virtualTimeBudgetExpired');
  await send('Emulation.setVirtualTimePolicy', { policy: 'advance', budget: 1000 / FPS });
  await expired;
  const { data } = await send('Page.captureScreenshot', { format: 'jpeg', quality: 92, optimizeForSpeed: true });
  writeFileSync(join(OUT, `f${String(n).padStart(5, '0')}.jpg`), Buffer.from(data, 'base64'));
  n++;
  if (n % 30 === 0) { process.stdout.write(`\r${(n / FPS).toFixed(0)} s`); if (await evaluate('window.timelineDone === true')) break; }
  if (n > FPS * 150) { console.log('\nstopped at 150 s'); break; }
}
console.log(`\n${n} frames, ${(n / FPS).toFixed(1)} s -> ${OUT}`);
chrome.kill();
process.exit(0);
