// Real-time screenshots of app states (no virtual time, so animations and timings are real).
// Needs the repo served on 127.0.0.1:8765. Usage: node video/shot.mjs <outDir> name=query#hash ...
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';

const OUT = resolve(process.argv[2]); mkdirSync(OUT, { recursive: true });
const PORT = 9713;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const chrome = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${join(tmpdir(), 'trailmark-shot-' + Date.now())}`,
  '--window-size=1440,1000', '--hide-scrollbars', '--force-color-profile=srgb',
  '--disable-background-timer-throttling', '--disable-renderer-backgrounding', 'about:blank'], { stdio: 'ignore' });
let target;
for (let i = 0; i < 80 && !target; i++) { try { target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: 'PUT' })).json(); } catch { await sleep(250); } }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r, { once: true }));
let seq = 0; const pending = new Map();
const send = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); } });
await send('Page.enable');
for (const spec of process.argv.slice(3)) {
  const name = spec.slice(0, spec.indexOf('=')), rest = spec.slice(spec.indexOf('=') + 1);
  const [h, w] = (process.env.SHOT_SIZE || '1440x1500').split('x').map(Number);
  await send('Emulation.setDeviceMetricsOverride', { width: h, height: w, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: `http://127.0.0.1:8765/web/?nointro&s=${Date.now()}${rest.startsWith('#') ? '' : '&'}${rest}` });
  await sleep(+(process.env.SHOT_WAIT || 7000));
  const { data } = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(join(OUT, name + '.png'), Buffer.from(data, 'base64'));
  console.log('saved', name);
}
ws.close(); chrome.kill();
process.exit(0);
