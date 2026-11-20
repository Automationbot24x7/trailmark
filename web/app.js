// Trailmark browser view. Relate runs here as WebAssembly: the page rebuilds the
// graph from an export of store/trailmark.rl, then runs the same .cypher files
// the command line and the agent server use.
import init, { RelateDb } from './vendor/relate-wasm/relate.js';

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const S = { db: null, graph: null, Q: null, findings: [], invoices: [], states: {}, sel: null, tab: 'why', linked: new Map(), timings: {} };

// ---------------------------------------------------------------- engine
function run(cypher, params) {
  const env = JSON.parse(S.db.execute(cypher, params ? JSON.stringify(params) : null));
  if (env.error) throw new Error(env.error);
  return env;
}
const rows = (cypher, params) => run(cypher, params).rows;

function loadGraph() {
  if (S.db) S.db.free();
  S.db = new RelateDb();
  for (const s of S.Q.schema) run(s);
  for (const g of S.graph.nodes) run(`UNWIND $rows AS r CREATE (n:${g.label}) SET n = r`, { rows: g.rows });
  for (const g of S.graph.rels) {
    run(`UNWIND $rows AS r MATCH (a:${g.from} {id: r.a}) MATCH (b:${g.to} {id: r.b}) CREATE (a)-[x:${g.type}]->(b) SET x = r.props`, { rows: g.rows });
  }
}

function scan() {
  const out = [];
  for (const c of S.Q.checks) {
    const env = run(c.text);
    S.timings[c.file] = env.elapsed_ms;
    for (const r of env.rows) out.push({ ...r, title: c.title, file: c.file });
  }
  out.sort((a, b) => (a.severity !== 'high') - (b.severity !== 'high') || b.amount - a.amount);
  S.findings = out;
  S.invoices = rows(`MATCH (i:Invoice)-[:ISSUED_BY]->(v:Vendor)
    OPTIONAL MATCH (p:Payment)-[:SETTLES]->(i)
    WITH i, v, collect(p.id) AS payments
    RETURN i.id AS id, v.name AS vendor, i.vendor_inv_no AS vendor_no, i.date AS date, i.total AS total, payments, v.terms_days AS terms
    ORDER BY i.id`);
  S.states = {};
  for (const i of S.invoices) {
    const f = out.filter((x) => x.invoice === i.id);
    i.due = addDays(i.date, i.terms);
    S.states[i.id] = f.length ? 'exception' : i.payments.length ? 'reconciled' : i.due > S.Q.as_of ? 'matched' : 'overdue';
  }
}

function explain(id) {
  const inv = S.invoices.find((i) => i.id === id);
  const found = S.findings.filter((f) => f.invoice === id);
  const extra = [...new Set(found.flatMap((f) => [...(f.path || []), ...(f.suggestion ? [f.suggestion.grn] : [])]))];
  const env = run(S.Q.trail.text, { id, extra });
  S.timings.trail = env.elapsed_ms;
  const t = env.rows[0];
  return { inv, status: S.states[id], findings: found, nodes: t.nodes, rels: t.rels.filter(Boolean) };
}

// ---------------------------------------------------------------- formatting
function addDays(iso, n) { const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + Number(n)); return d.toISOString().slice(0, 10); }
function inr(n) {
  const neg = n < 0; let s = String(Math.round(Math.abs(Number(n))));
  if (s.length > 3) s = s.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ',') + ',' + s.slice(-3);
  return (neg ? '-' : '') + '₹' + s;
}
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const nice = (iso) => { const [y, m, d] = iso.split('-'); return `${+d} ${MONTHS[+m - 1]} ${y}`; };
const ID_RE = /\b(INV-\d+|PO-\d+|GRN-\d+|PAY-\d+|BL-\d+|BA-\d+|BC-\d+|G2B-\d+|E-\d{2}|V-\d{3})\b/g;
function rich(text) {
  return esc(text)
    .replace(/Rs (\d+)/g, (_, n) => inr(n))
    .replace(/(^|[\s(])(\d{4,})(?=[\s,.)]|$)/g, (_, pre, n) => pre + Number(n).toLocaleString('en-IN'))
    .replace(/\b(20\d\d-\d\d-\d\d)\b/g, (_, d) => nice(d))
    .replace(ID_RE, (m) => `<span class="chip" data-id="${m}">${m}</span>`);
}
function wrapWords(t, n) { const out = []; let cur = ''; for (const w of t.split(' ')) { if ((cur + ' ' + w).trim().length > n && cur) { out.push(cur); cur = w; } else cur = (cur + ' ' + w).trim(); } if (cur) out.push(cur); return out; }
const trunc = (s, n) => (s = String(s ?? ''), s.length > n ? s.slice(0, n - 1) + '…' : s);

// ---------------------------------------------------------------- ledger list
function renderLedger() {
  const n = (s) => Object.values(S.states).filter((x) => x === s).length;
  const risk = S.findings.reduce((a, f) => a + Number(f.amount || 0), 0);
  $('#risk').textContent = inr(risk);
  $('#exc-n').textContent = n('exception');
  $('#asof').textContent = nice(S.Q.as_of);
  $('#tally').innerHTML = `
    <div class="t-exc"><b>${n('exception')}</b><span>exceptions</span></div>
    <div class="t-ok"><b>${n('reconciled')}</b><span>reconciled</span></div>
    <div><b>${n('matched')}</b><span>matched</span></div>`;
  const groups = [['exception', 'Exceptions'], ['matched', 'Matched, not yet due'], ['overdue', 'Overdue'], ['reconciled', 'Reconciled']];
  let html = '';
  for (const [st, name] of groups) {
    let list = S.invoices.filter((i) => S.states[i.id] === st);
    if (!list.length) continue;
    if (st === 'exception') {
      const order = S.findings.map((f) => f.invoice);
      list = list.sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
    }
    html += `<div class="group-h"><span>${name} · ${list.length}</span><span>${st === 'exception' ? 'at risk' : 'invoice'}</span></div>`;
    for (const i of list) {
      const f = S.findings.find((x) => x.invoice === i.id);
      html += `<button class="row${S.sel === i.id ? ' sel' : ''}" data-inv="${i.id}">
        <span class="dot ${st}${f ? ' ' + f.severity : ''}" title="${f ? f.severity + ' severity' : st}"></span>
        <span class="who"><span class="id">${i.id}</span><span class="v">${esc(i.vendor)}</span>
        ${f ? `<span class="why">${rich(f.headline).replace(/<[^>]+>/g, '')}</span>` : ''}</span>
        <span class="amt">${inr(f ? f.amount : i.total)}</span></button>`;
    }
  }
  $('#list').innerHTML = html;
}

// ---------------------------------------------------------------- trail canvas
const LANES = [['Vendor', 'Vendor'], ['PurchaseOrder', 'Purchase order'], ['GoodsReceipt', 'Goods receipt'], ['Invoice', 'Invoice'], ['Payment', 'Payment'], ['BankLine', 'Bank statement']];
const SLOT = { Vendor: [0, 0], PurchaseOrder: [1, 0], GoodsReceipt: [2, 0], Invoice: [3, 0], Payment: [4, 0], BankLine: [5, 0],
  GstrLine: [3, 1], BankAccount: [4, 1], BankChange: [5, 1], Employee: [5, 2] };
const KIND = { Vendor: 'Vendor', PurchaseOrder: 'Purchase order', GoodsReceipt: 'Goods receipt', Invoice: 'Invoice', Payment: 'Payment',
  BankLine: 'Bank line', GstrLine: 'Our GSTR-2B', BankAccount: 'Paid to account', BankChange: 'Bank detail change', Employee: 'Employee' };
const W = 172, H = 74, GX = 66, PADX = 22, TOP = 72, VG = 14, BAND = 52, RIGHT = 74;

function lines(n) {
  const p = n.props;
  switch (n.label) {
    case 'Vendor': return [p.name, `${p.city} · ${p.gstin}`];
    case 'PurchaseOrder': return [`${p.qty} × ${p.item}`, `${nice(p.date)} · ${inr(p.total)}`];
    case 'GoodsReceipt': return [`${p.qty} received · ${trunc(p.item, 14)}`, `${nice(p.date)} · ref ${p.po_ref}`];
    case 'Invoice': return [`${p.vendor_inv_no} · ${p.qty} unit${p.qty === 1 ? '' : 's'}`, `${nice(p.date)} · ${inr(p.total)}`];
    case 'Payment': return [inr(p.amount), `${nice(p.date)} · UTR …${String(p.utr).slice(-6)}`];
    case 'BankLine': return [`${p.direction} ${inr(p.amount)}`, `${nice(p.date)} · ${p.narration.includes('RETURN') ? 'RETURN · A/C CLOSED' : 'NEFT ' + p.utr.slice(-6)}`];
    case 'GstrLine': return [`${p.vendor_inv_no} · tax ${inr(p.tax)}`, `period ${p.period}`];
    case 'BankAccount': return [p.bank, n.vendorSince ? `vendor's since ${nice(n.vendorSince)}` : `··${p.last4}`];
    case 'BankChange': return [p.reason, nice(p.date)];
    case 'Employee': return [p.name, p.role];
  }
  return ['', ''];
}

function layout(ex) {
  const ev = new Set(ex.findings.flatMap((f) => f.path || []));
  const high = ex.findings.some((f) => f.severity === 'high');
  const sugg = ex.findings.filter((f) => f.suggestion && !S.linked.has(f.suggestion.grn)).map((f) => f.suggestion);
  const ghosts = ex.findings.filter((f) => f.missing).map((f) => ({ id: '__ghost_' + f.missing.label, label: f.missing.label, ghost: true, text: f.missing.text, after: f.missing.after }));
  const since = Object.fromEntries(ex.rels.filter((r) => r.type === 'HAS_ACCOUNT' && /^V-/.test(r.from)).map((r) => [r.to, r.props.since]));
  const items = [...ghosts, ...ex.nodes.map((n) => ({ ...n, vendorSince: since[n.id] }))];
  const bySlot = {};
  // people sit side by side under the money, the most-connected one under the account
  const deg = (id) => ex.rels.filter((r) => r.from === id || r.to === id).length;
  const people = items.filter((it) => it.label === 'Employee').sort((a, b) => deg(b.id) - deg(a.id) || a.id.localeCompare(b.id));
  const PEOPLE_COLS = [4, 5, 3, 2, 1];
  people.forEach((it, i) => { it.slot = [PEOPLE_COLS[i % 5], 2]; });
  for (const it of items) {
    const s = it.slot || SLOT[it.label]; if (!s) continue;
    const key = s.join(',');
    (bySlot[key] ||= []).push(it);
  }
  const rowsUsed = [0, 1, 2].filter((r) => Object.keys(bySlot).some((k) => +k.split(',')[1] === r));
  const rowH = {};
  for (const r of [0, 1, 2]) rowH[r] = Math.max(1, ...Object.entries(bySlot).filter(([k]) => +k.split(',')[1] === r).map(([, v]) => v.length)) * (H + VG) - VG;
  const rowY = {}; let y = TOP;
  for (const r of [0, 1, 2]) { rowY[r] = y; if (rowsUsed.includes(r)) y += rowH[r] + BAND; else if (r === 0) y += H + BAND; }
  // place lane by lane; inside a lane: the ghost, then the focus invoice, then by the average height of
  // already-placed neighbours (so lines don't cross), then evidence first, then id
  const pos = {};
  const keys = Object.keys(bySlot).sort((p, q) => p.split(',')[0] - q.split(',')[0] || p.split(',')[1] - q.split(',')[1]);
  const bary = (it) => {
    const ys = ex.rels.filter((e) => e.from === it.id || e.to === it.id).map((e) => pos[e.from === it.id ? e.to : e.from]).filter(Boolean).map((p) => p.y);
    return ys.length ? ys.reduce((s, v) => s + v, 0) / ys.length : 1e9;
  };
  for (const k of keys) {
    const [c, r] = k.split(',').map(Number);
    const list = bySlot[k];
    const b = Object.fromEntries(list.map((it) => [it.id, bary(it)]));
    list.sort((p, q) => (q.ghost ? 1 : 0) - (p.ghost ? 1 : 0) || (p.id === ex.inv.id ? -1 : q.id === ex.inv.id ? 1 : 0) || (b[p.id] - b[q.id]) || (ev.has(q.id) - ev.has(p.id)) || p.id.localeCompare(q.id));
    list.forEach((it, idx) => { pos[it.id] = { x: PADX + c * (W + GX), y: rowY[r] + idx * (H + VG), it }; });
  }
  const width = PADX * 2 + 6 * W + 5 * GX + RIGHT;
  return { pos, ev, high, sugg, ghosts, height: y - BAND + 26, width, rowY, rowsUsed };
}

function edgePath(a, b) {
  const ax = a.x, ay = a.y, bx = b.x, by = b.y;
  if (Math.abs(ax - bx) < 1) { // same column
    if (Math.abs(ay - by) < 1) return null;
    const top = ay < by ? a : b, bot = ay < by ? b : a;
    if (bot.y - top.y <= H + VG + 1) { // stacked neighbours: arc on the right
      const x = top.x + W, y1 = top.y + H / 2, y2 = bot.y + H / 2;
      return { d: `M${x} ${y1} C${x + 26} ${y1}, ${x + 26} ${y2}, ${x} ${y2}`, mx: x + 24, my: (y1 + y2) / 2, anchor: 'start', rev: ay > by };
    }
    const between = Object.values(LAST.pos).some((q) => Math.abs(q.x - top.x) < 1 && q.y > top.y + 1 && q.y < bot.y - 1);
    if (between) { // cards in the way: swing out into the left gutter
      const x = top.x, y1 = bot.y + H * 0.35, y2 = top.y + H * 0.82;
      return { d: `M${x} ${y1} C${x - 34} ${y1}, ${x - 34} ${y2}, ${x} ${y2}`, mx: x - GX / 2, my: (y1 + y2) / 2, anchor: 'middle', rev: ay < by };
    }
    const x = top.x + W / 2, y1 = top.y + H, y2 = bot.y;
    return { d: `M${x} ${y1} L${x} ${y2}`, mx: x + 6, my: (y1 + y2) / 2 + 3, anchor: 'start', rev: ay > by };
  }
  const left = ax < bx ? a : b, right = ax < bx ? b : a;
  if (right.x - left.x > W + GX + 1 && Math.abs(ay - by) < 1) { // skips a lane: arc over the top
    const x1 = left.x + W * 0.62, x2 = right.x + W * 0.38, y = left.y, top = y - 30;
    return { d: `M${x1} ${y} C${x1} ${top}, ${x2} ${top}, ${x2} ${y}`, mx: (x1 + x2) / 2, my: top + 4, anchor: 'middle', rev: ax > bx, arc: true };
  }
  const cross = Math.abs(left.y - right.y) > 1;
  const yl = cross ? left.y + H * (left.y > right.y ? 0.22 : 0.8) : left.y + H / 2;
  const yr = cross ? right.y + H * (right.y > left.y ? 0.22 : 0.8) : right.y + H / 2;
  const x1 = left.x + W, y1 = yl, x2 = right.x, y2 = yr;
  const dx = Math.max(24, (x2 - x1) / 2);
  const above = !cross && x2 - x1 < W;
  return { d: `M${x1} ${y1} C${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`, mx: (x1 + x2) / 2, my: above ? y1 - 16 : (y1 + y2) / 2 - 4, anchor: 'middle', rev: ax > bx };
}

function labelSvg(p, label, cls) {
  const parts = !p.arc && label.length > 8 && label.includes('_') ? [label.slice(0, label.indexOf('_') + 1), label.slice(label.indexOf('_') + 1)] : [label];
  const cw = 6.1, lw = Math.max(...parts.map((t) => t.length)) * cw + 8, lh = parts.length * 10 + 4;
  const lx = p.anchor === 'middle' ? p.mx - lw / 2 : p.anchor === 'end' ? p.mx - lw + 4 : p.mx - 4;
  const top = p.my - (parts.length - 1) * 5 - 9;
  return `<rect x="${lx}" y="${top}" width="${lw}" height="${lh}"/><text class="elabel ${cls}" x="${p.mx}" y="${top + 9}" text-anchor="${p.anchor}">${parts.map((t, i) => `<tspan x="${p.mx}" dy="${i ? 10 : 0}">${esc(t)}</tspan>`).join('')}</text>`;
}

let LAST = { pos: {} };
// fit a line in a card: as is, gently condensed (up to 25%), or cut
function fit(cls, x, y, s, n) {
  s = String(s ?? '');
  if (s.length <= n) return `<text class="${cls}" x="${x}" y="${y}">${esc(s)}</text>`;
  const t = s.length <= Math.round(n * 1.25) ? s : trunc(s, Math.round(n * 1.25));
  return `<text class="${cls}" x="${x}" y="${y}" textLength="${W - 24}" lengthAdjust="spacingAndGlyphs">${esc(t)}</text>`;
}
function renderTrail(ex, animate) {
  const L = layout(ex);
  LAST = L;
  let edges = '', labels = '', cards = '', heads = '';
  LANES.forEach(([, name], c) => {
    const x = PADX + c * (W + GX);
    heads += `<text class="lane-h" x="${x}" y="24">${name}</text>`;
  });
  if (L.rowsUsed.includes(1) || L.rowsUsed.includes(2)) {
    const y = L.rowY[L.rowsUsed.find((r) => r > 0)] - 16;
    heads += `<line class="lane-rule" x1="${PADX}" x2="${L.width - PADX}" y1="${y - 14}" y2="${y - 14}"/><text class="band-h" x="${PADX}" y="${y}">Tax filing and where the money went</text>`;
  }
  // empty main lanes get a quiet note
  LANES.forEach(([label], c) => {
    if (Object.values(L.pos).some((p) => p.it.label === label)) return;
    const x = PADX + c * (W + GX), y = L.rowY[0];
    const note = (label === 'Payment' || label === 'BankLine') && ex.inv.due > S.Q.as_of ? `none yet · due ${nice(ex.inv.due)}` : 'none';
    cards += `<g class="card dim"><rect class="box" x="${x}" y="${y}" width="${W}" height="${H}" style="stroke-dasharray:2 3"/><text class="l2" x="${x + 12}" y="${y + 42}">${note}</text></g>`;
  });
  let k = 0;
  const edge = (a, b, cls, label, delay) => {
    const p = edgePath(a, b); if (!p) return;
    const len = 400, n = k++;
    const mk = `url(#arr-${cls.includes('brk') ? 'r' : cls.includes('sug') ? 'a' : cls.includes('fixed') ? 'g' : cls.includes('high') ? 'r' : 'k'})`;
    edges += `<path class="edge ${cls}${animate ? ' draw' : ''}" d="${p.d}" data-a="${a.it.id}" data-b="${b.it.id}" data-t="${esc(label || '')}" data-k="${n}" style="--len:${len};animation-delay:${delay}ms" ${p.rev ? 'marker-start' : 'marker-end'}="${mk}"><title>${esc(label || '')}</title></path>`;
    if (!label) return;
    labels += `<g class="elab ${cls}" data-k="${n}">${labelSvg(p, label, cls)}</g>`;
  };
  // relationships (drawn from source to target; arrows show the stored direction)
  const colOf = (id) => (L.pos[id] ? L.pos[id].x : 0);
  for (const r of ex.rels) {
    const a = L.pos[r.from], b = L.pos[r.to]; if (!a || !b) continue;
    // the vendor is reached through the PO; other lines back to the vendor card are written on the cards instead
    if (a.it.label === 'Vendor' || b.it.label === 'Vendor') { if (r.type !== 'PLACED_WITH') continue; }
    const isFix = r.type === 'RECEIVED_AGAINST' && S.linked.has(r.from);
    const ev = L.ev.has(r.from) && L.ev.has(r.to);
    const cls = isFix ? 'fixed' : ev ? `ev${L.high ? ' high' : ''}` : '';
    const delay = animate ? 120 + (Math.min(colOf(r.from), colOf(r.to)) / (W + GX)) * 90 : 0;
    edge(a, b, cls, r.type, delay);
  }
  for (const g of L.ghosts) {
    const a = L.pos[g.after], b = L.pos[g.id];
    if (a && b) edge(b, a, 'brk', '', 0);
  }
  for (const s of L.sugg) {
    const a = L.pos[s.grn], b = L.pos[s.po];
    if (a && b) edge(a, b, 'sug', '', 0);
  }
  // cards
  for (const { x, y, it } of Object.values(L.pos)) {
    const col = Math.round((x - PADX) / (W + GX));
    const delay = animate ? col * 90 : 0;
    if (it.ghost) {
      cards += `<g class="card ghost${animate ? ' appear' : ''}" style="animation-delay:${delay + 260}ms" data-id="${it.id}">
        <rect class="box" x="${x}" y="${y}" width="${W}" height="${H}"/>
        <text class="k" x="${x + 12}" y="${y + 18}">Expected · not found</text>
        ${wrapWords(it.text.replace('expected: ', ''), 21).slice(0, 2).map((t, i) => `<text class="l1" x="${x + 12}" y="${y + 40 + i * 17}">${esc(t)}</text>`).join('')}</g>`;
      continue;
    }
    const [l1, l2] = lines(it);
    const isCand = L.sugg.some((s) => s.grn === it.id);
    const isFixed = S.linked.has(it.id);
    const ev = L.ev.has(it.id);
    const cls = ['card', isFixed ? 'fixed' : isCand ? 'cand' : '', ev && !isFixed ? 'ev' : '', ev && L.high ? 'high' : '', it.id === ex.inv.id ? 'focus' : '', animate ? 'appear' : ''].join(' ');
    const kind = isCand ? 'Candidate receipt' : isFixed ? 'Receipt · linked now' : KIND[it.label];
    cards += `<g class="${cls}" style="animation-delay:${delay}ms" data-id="${it.id}">
      <rect class="box" x="${x}" y="${y}" width="${W}" height="${H}"/>
      <text class="k" x="${x + 12}" y="${y + 18}">${esc(kind)}</text>
      <text class="i" x="${x + 12}" y="${y + 37}">${esc(it.id)}</text>
      ${fit('l1', x + 12, y + 54, l1, 23)}
      ${fit('l2', x + 12, y + 68, l2, 26)}
      ${ev && !isFixed ? `<rect class="flag" x="${x + W - 10}" y="${y}" width="10" height="10"/>` : ''}</g>`;
  }
  const marker = (id, color) => `<marker id="arr-${id}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L8 4 L0 8 z" fill="${color}"/></marker>`;
  return `<svg class="trail" viewBox="0 0 ${L.width} ${L.height}" role="img" aria-label="Trail of ${ex.inv.id}">
    <defs>${marker('k', '#a6a198')}${marker('r', '#c7341f')}${marker('a', '#a8650b')}${marker('g', '#2c7a4b')}
      <filter id="lift" x="-12%" y="-15%" width="124%" height="150%"><feDropShadow dx="0" dy="1" stdDeviation=".8" flood-color="#3b2a1a" flood-opacity=".22"/><feDropShadow dx="0" dy="5" stdDeviation="5" flood-color="#3b2a1a" flood-opacity=".11"/></filter>
      <filter id="lift-hi" x="-20%" y="-25%" width="140%" height="180%"><feDropShadow dx="0" dy="2" stdDeviation="1.4" flood-color="#3b2a1a" flood-opacity=".22"/><feDropShadow dx="0" dy="14" stdDeviation="12" flood-color="#3b2a1a" flood-opacity=".2"/></filter>
      <filter id="hole" x="0" y="0" width="100%" height="100%"><feFlood flood-color="#5a1a10" flood-opacity=".42"/><feComposite in2="SourceAlpha" operator="out"/><feGaussianBlur stdDeviation="3.2"/><feOffset dx="0" dy="2.5" result="s"/><feComposite in="s" in2="SourceAlpha" operator="in" result="in"/><feMerge><feMergeNode in="SourceGraphic"/><feMergeNode in="in"/></feMerge></filter></defs>
    ${heads}<g class="edges">${edges}</g><g class="cards">${cards}</g><g class="labels">${labels}</g>
    <g class="walker" opacity="0"><circle class="w-halo" r="11"/><circle class="w-dot" r="4.5"/></g></svg>`;
}

// ---------------------------------------------------------------- live trail: walk, hover, drag
// The walk replays the evidence path the check returned, hop by hop, and stops where the link is missing.
let WALK = 0;
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
function walkSteps(ex) {
  const steps = [];
  const vendor = (id) => LAST.pos[id]?.it.label === 'Vendor';
  for (const f of ex.findings) {
    // start from the invoice when the check returned the path the other way round; the vendor is context, not a hop
    let p = (f.path || []).filter((id) => !vendor(id));
    if (p.length && p[p.length - 1] === ex.inv.id && p[0] !== ex.inv.id) p = p.reverse();
    // the evidence can branch (one account, two people): each hop starts from the latest visited card it is joined to
    const joined = (x, y) => ex.rels.some((r) => (r.from === x && r.to === y) || (r.from === y && r.to === x));
    for (let i = 1; i < p.length; i++) {
      const from = p.slice(0, i).reverse().find((x) => joined(x, p[i])) || p[i - 1];
      steps.push([from, p[i]]);
    }
    if (f.missing) steps.push([f.missing.after, '__ghost_' + f.missing.label, KIND[f.missing.label] || 'link']);
  }
  if (!steps.length) { // clean trail: from the invoice, visit every document on the main row it is joined to
    const main = new Set(Object.values(LAST.pos).filter((q) => q.y === LAST.rowY[0] && !q.it.ghost && q.it.label !== 'Vendor').map((q) => q.it.id));
    const nb = (x) => ex.rels.filter((r) => r.from === x || r.to === x).map((r) => (r.from === x ? r.to : r.from)).filter((y) => main.has(y));
    const seen = [ex.inv.id];
    for (;;) {
      const from = [...seen].reverse().find((x) => nb(x).some((y) => !seen.includes(y)));
      if (!from) break;
      const to = nb(from).filter((y) => !seen.includes(y)).sort((u, v) => LAST.pos[u].x - LAST.pos[v].x)[0];
      steps.push([from, to]); seen.push(to);
    }
  }
  return steps;
}
function walk(ex) {
  const svg = $('svg.trail'), log = $('#walk-log'); if (!svg || !log) return;
  const my = ++WALK, steps = walkSteps(ex);
  const w = svg.querySelector('.walker');
  const centre = (id) => { const q = LAST.pos[id]; return q && { x: q.x + W / 2, y: q.y + H / 2 }; };
  const card = (id) => svg.querySelector(`.card[data-id="${id}"]`);
  const hit = (id, cls = 'hit') => { const c = card(id); if (!c) return; c.classList.remove(cls); void c.getBBox(); c.classList.add(cls); };
  const pathFor = (a, b) => [...svg.querySelectorAll('.edge')].find((e) => (e.dataset.a === a && e.dataset.b === b) || (e.dataset.a === b && e.dataset.b === a));
  log.innerHTML = `<span class="wl-h">Walk</span><span class="hop"><b class="chip" data-id="${steps[0]?.[0] || ex.inv.id}">${steps[0]?.[0] || ex.inv.id}</b></span>`;
  if (!steps.length) return;
  if (reduced()) { // no motion: write the whole walk at once
    for (const [a, b, miss] of steps) addHop(log, a, b, miss, pathFor(a, b));
    return;
  }
  let i = 0;
  const next = () => {
    if (my !== WALK) return;
    if (i >= steps.length) { w.setAttribute('opacity', '0'); return; }
    const [a, b, miss] = steps[i++];
    const el = pathFor(a, b), A = centre(a), B = centre(b);
    if (!A || !B) return next();
    const len = el ? el.getTotalLength() : 0;
    const fwd = el ? el.dataset.a === a : true;
    const at = (t) => {
      if (!el) return { x: A.x + (B.x - A.x) * t, y: A.y + (B.y - A.y) * t };
      return el.getPointAtLength(len * (fwd ? t : 1 - t));
    };
    const dur = Math.max(420, Math.min(900, len * 2.2)), t0 = performance.now();
    w.classList.toggle('miss', !!miss);
    hit(a);
    const tick = (now) => {
      if (my !== WALK) return;
      const t = Math.min(1, (now - t0) / dur), e = t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      const pt = at(e); w.setAttribute('transform', `translate(${pt.x} ${pt.y})`); w.setAttribute('opacity', '1');
      if (t < 1) return requestAnimationFrame(tick);
      addHop(log, a, b, miss, el);
      if (miss) { hit(b, 'miss-hit'); w.setAttribute('opacity', '0'); return; }
      hit(b); setTimeout(next, 160);
    };
    requestAnimationFrame(tick);
  };
  setTimeout(next, 700);
}
function addHop(log, a, b, miss, el) {
  const last = log.querySelector('.hop:last-child .chip')?.dataset.id;
  if (last && last !== a) log.insertAdjacentHTML('beforeend', `<span class="hop"><i class="r">·</i><b class="chip" data-id="${a}">${a}</b></span>`);
  const t = el?.dataset.t || '';
  const fwd = !el || el.dataset.a === a;
  const rel = t ? (fwd ? `-${t}→` : `←${t}-`) : '→';
  log.insertAdjacentHTML('beforeend', miss
    ? `<span class="hop"><i class="r miss">→</i><b class="miss">no ${esc(String(miss).toLowerCase())} found</b></span>`
    : `<span class="hop"><i class="r">${esc(rel)}</i><b class="chip" data-id="${b}">${b}</b></span>`);
}

function lightUp(id) {
  const svg = $('svg.trail'); if (!svg) return;
  svg.classList.toggle('hov', !!id);
  svg.querySelectorAll('.lit').forEach((x) => x.classList.remove('lit'));
  if (!id) return;
  const near = new Set([id]);
  svg.querySelectorAll('.edge').forEach((e) => {
    if (e.dataset.a !== id && e.dataset.b !== id) return;
    e.classList.add('lit'); near.add(e.dataset.a); near.add(e.dataset.b);
    svg.querySelector(`.elab[data-k="${e.dataset.k}"]`)?.classList.add('lit');
  });
  near.forEach((n) => svg.querySelector(`.card[data-id="${n}"]`)?.classList.add('lit'));
}

let DRAG = null;
function svgPoint(svg, e) { const p = svg.createSVGPoint(); p.x = e.clientX; p.y = e.clientY; return p.matrixTransform(svg.getScreenCTM().inverse()); }
function reroute(svg, id) {
  svg.querySelectorAll('.edge').forEach((e) => {
    if (e.dataset.a !== id && e.dataset.b !== id) return;
    const p = edgePath(LAST.pos[e.dataset.a], LAST.pos[e.dataset.b]); if (!p) return;
    e.setAttribute('d', p.d);
    e.removeAttribute('marker-start'); e.removeAttribute('marker-end');
    e.setAttribute(p.rev ? 'marker-start' : 'marker-end', `url(#arr-${e.classList.contains('brk') || e.classList.contains('high') ? 'r' : e.classList.contains('sug') ? 'a' : e.classList.contains('fixed') ? 'g' : 'k'})`);
    const lab = svg.querySelector(`.elab[data-k="${e.dataset.k}"]`);
    if (lab) lab.innerHTML = labelSvg(p, e.dataset.t, [...e.classList].filter((c) => ['ev', 'high', 'brk', 'sug', 'fixed'].includes(c)).join(' '));
  });
}
document.addEventListener('pointerdown', (e) => {
  const g = e.target.closest('svg.trail .card[data-id]'); if (!g || e.button !== 0 || e.pointerType === 'touch') return;
  const svg = g.ownerSVGElement, id = g.dataset.id, q = LAST.pos[id]; if (!q) return;
  WALK++; svg.querySelector('.walker')?.setAttribute('opacity', '0');
  svg.querySelectorAll('.edge.draw').forEach((x) => x.classList.remove('draw'));
  const p = svgPoint(svg, e);
  q.ox ??= q.x; q.oy ??= q.y;
  DRAG = { svg, g, id, dx: p.x - q.x, dy: p.y - q.y };
  g.classList.add('dragging'); svg.querySelector('.cards').appendChild(g);
  g.setPointerCapture?.(e.pointerId);
  e.preventDefault();
});
document.addEventListener('pointermove', (e) => {
  if (!DRAG) return;
  const { svg, g, id } = DRAG, p = svgPoint(svg, e), q = LAST.pos[id];
  const vb = svg.viewBox.baseVal;
  q.x = Math.max(4, Math.min(vb.width - W - 4, p.x - DRAG.dx));
  q.y = Math.max(34, Math.min(vb.height - H - 4, p.y - DRAG.dy));
  g.setAttribute('transform', `translate(${q.x - q.ox} ${q.y - q.oy})`);
  reroute(svg, id);
});
document.addEventListener('pointerup', () => { if (!DRAG) return; DRAG.g.classList.remove('dragging'); DRAG = null; });

// ---------------------------------------------------------------- cypher highlighting
function highlight(src) {
  return src.split('\n').map((line) => {
    if (/^\s*\/\//.test(line)) return `<span class="cm">${esc(line)}</span>`;
    let h = esc(line);
    h = h.replace(/(&#39;[^&]*?&#39;)/g, '<span class="st">$1</span>');
    h = h.replace(/\b(MATCH|OPTIONAL|WHERE|RETURN|WITH|UNWIND|CREATE|CALL|SEARCH|VECTOR|INDEX|FOR|LIMIT|ORDER BY|DESC|AND|OR|NOT|EXISTS|CASE|WHEN|THEN|ELSE|END|IN|AS|DISTINCT|SCORE|SHORTEST|null|IS)\b/g, '<span class="kw">$1</span>');
    h = h.replace(/(\(\w*):(\w+)/g, '$1:<span class="lb">$2</span>');
    h = h.replace(/\[(\w*):([A-Z_|]+)/g, '[$1:<span class="rt">$2</span>');
    return h;
  }).join('\n');
}

// ---------------------------------------------------------------- stage
function renderStage(animate = true) {
  const ex = explain(S.sel);
  const inv = ex.inv;
  const statusText = { exception: 'Exception', reconciled: 'Reconciled', matched: 'Matched · not yet due', overdue: 'Overdue' }[ex.status];
  let findingsHtml = '';
  if (!ex.findings.length) {
    const msg = ex.status === 'reconciled'
      ? ['Every link holds.', 'Ordered, received, billed, paid, cleared by the bank, and reported by the supplier so it shows in our GSTR-2B.']
      : ['Matched. Nothing is broken.', `Ordered, received and billed agree. Due ${nice(inv.due)}, so no payment is expected yet.`];
    findingsHtml = `<div class="ok-note"><b>${msg[0]}</b>${msg[1]}</div>`;
    const fixed = [...S.linked.entries()].find(([, v]) => v.invoice === inv.id);
    if (fixed) findingsHtml += fixedNote(fixed[0], fixed[1]);
  }
  for (const f of ex.findings) {
    findingsHtml += `<article class="finding">
      <div class="f-top"><span class="sev ${f.severity}">${f.severity.toUpperCase()}</span><span class="f-title">${esc(f.title)}</span><span class="f-amt">${inr(f.amount)}</span></div>
      <h3 class="f-head">${rich(f.headline)}</h3>
      <p class="f-detail">${rich(f.detail)}</p>
      <div class="f-path"><span class="lbl">Evidence</span>${(f.path || []).map((id) => `<span class="chip" data-id="${id}">${id}</span>`).join('<span class="arr">·</span>')}</div>
      ${f.suggestion ? `<div class="fix"><div><p><b>Suggested fix:</b> ${rich(f.suggestion.text)}</p>
        <small>Vector search over receipt text from the same vendor scored it ${Number(f.suggestion.similarity).toFixed(2)}${(f.suggestion.rejected || []).length ? `; the graph ruled out ${f.suggestion.rejected.map(esc).join(', ')}` : ''}. The link is written to the graph in this tab only; reload to undo.</small></div>
        <button class="btn" data-link="${f.suggestion.grn}|${f.suggestion.po}">Link ${f.suggestion.grn}</button></div>` : ''}
    </article>`;
  }
  $('#stage').innerHTML = `
    <div class="inv-head">
      <div>
        <div class="inv-kicker"><span class="status ${ex.status}" id="status">${statusText}</span><span>Invoice · ${esc(inv.vendor_no)}</span></div>
        <h1 class="inv-title">${inv.id} <span class="vn">${esc(inv.vendor)}</span></h1>
        <div class="inv-meta">${inr(inv.total)}<span class="sep">/</span>dated ${nice(inv.date)}<span class="sep">/</span>due ${nice(inv.due)}<span class="sep">/</span>${inv.payments.length ? 'paid by ' + inv.payments.join(', ') : 'unpaid'}</div>
      </div>
    </div>
    <div class="trail-wrap">
      <div class="trail-cap"><span><b>The trail</b> · ${ex.nodes.length} nodes, ${ex.rels.length} relationships, walked in ${fmtMs(S.timings.trail)} · <button class="rewalk" data-rewalk="1" type="button">Walk it again</button></span>
        <span class="legend"><span><i></i>link holds</span><span><i class="brk"></i>expected, not found</span><span><i class="sug"></i>suggested</span><span><i class="ok"></i>fixed</span></span></div>
      <div class="trail-scroll">${renderTrail(ex, animate)}</div>
      <div class="walk-row"><div class="walk-log" id="walk-log" aria-live="polite"></div><span class="trail-hint">Drag a card to move it · hover one to light up its links</span></div>
    </div>
    <div class="cols">
      <section><h2 class="sec-h"><span>${ex.findings.length ? 'Where it breaks' : 'Result'}</span><span>${ex.findings.length ? ex.findings.length + ' finding' + (ex.findings.length > 1 ? 's' : '') : ''}</span></h2>${findingsHtml}</section>
      <section id="side"></section>
    </div>`;
  renderSide(ex);
  S.ex = ex;
  walk(ex);
}

function fixedNote(grn, v) {
  return `<div class="fixed-note"><b>Linked ${grn} → ${v.po}</b> in this tab, recorded on the relationship as
    <code>{linked_by: 'browser', was_keyed_as: '${v.was}'}</code>. In the browser the change lives in memory; from the command line or an agent it is written to <code>store/trailmark.rl</code>.
    <div style="margin-top:8px"><button class="btn ghostbtn" data-reset="1">Reset sample books</button></div></div>`;
}

const fmtMs = (ms) => (ms == null ? 'n/a' : ms < 1 ? `${ms.toFixed(2)} ms` : `${ms.toFixed(1)} ms`);

const PRESETS = [
  ['Who is linked to PAY-3410?', `MATCH path = (p:Payment {id: 'PAY-3410'})
      ((a)-[:PAID_TO|HAS_ACCOUNT|NEW_ACCOUNT|ENTERED|APPROVED]-(b)){1,3}
      (e:Employee)
RETURN e.name AS person, [r IN relationships(path) | type(r)] AS route`],
  ['Payments that left as several debits', `MATCH (p:Payment)<-[:CLEARS]-(b:BankLine)
WITH p, collect(b.id) AS debits
WHERE size(debits) > 1
OPTIONAL MATCH (b2:BankLine)-[:CLEARS]->(p)
OPTIONAL MATCH (r:BankLine)-[:REVERSES]->(b2)
RETURN p.id, p.amount, debits, collect(r.id) AS returned`],
  ['Receipts linked to no PO', `MATCH (g:GoodsReceipt)
WHERE NOT EXISTS { (g)-[:RECEIVED_AGAINST]->() }
RETURN g.id, g.po_ref AS keyed_as, g.item, g.qty`],
  ['Invoices the supplier never reported', `MATCH (i:Invoice)-[:ISSUED_BY]->(v:Vendor)
WHERE NOT EXISTS { (:GstrLine)-[:REPORTS]->(i) }
RETURN i.id, v.name, i.gst AS credit_at_risk`],
  ['One payment, many invoices', `MATCH (p:Payment)-[s:SETTLES]->(i:Invoice)
WITH p, collect(i.id + ' ' + toString(s.amount)) AS settles
WHERE size(settles) > 1
RETURN p.id, p.amount, settles`],
];

function renderSide(ex) {
  const side = $('#side');
  const tabs = `<div class="tabs"><button class="tab ${S.tab === 'why' ? 'on' : ''}" data-tab="why">How the graph found it</button><button class="tab ${S.tab === 'ask' ? 'on' : ''}" data-tab="ask">Query the graph</button></div>`;
  if (S.tab === 'why') {
    const files = ex.findings.length ? [...new Set(ex.findings.map((f) => f.file))].map((f) => S.Q.checks.find((c) => c.file === f)) : [S.Q.trail];
    side.innerHTML = tabs + files.map((c) => `
      <p class="q-why">${esc(c.graph || c.plain)}</p>
      <div class="q-file"><span>${c.file}</span><span>${fmtMs(S.timings[c.file] ?? S.timings.trail)} in your browser</span></div>
      <pre class="cy">${highlight(c.text.split('\n').filter((l) => !/^\/\/\s*(title|plain|graph):/.test(l)).join('\n'))}</pre>`).join('<div style="height:18px"></div>');
  } else {
    side.innerHTML = tabs + `<div class="console">
      <div class="presets">${PRESETS.map(([n], i) => `<button class="preset" data-preset="${i}">${esc(n)}</button>`).join('')}</div>
      <textarea id="cq" spellcheck="false" wrap="off" aria-label="Cypher query">${esc(S.lastQuery || PRESETS[0][1])}</textarea>
      <div class="run-row"><button class="btn" id="runq">Run</button><span id="qmeta">Runs on the in-memory copy in this tab · Ctrl+Enter to run · reload to reset</span></div>
      <div id="qres"></div></div>`;
    runConsole();
  }
}

function runConsole() {
  const ta = $('#cq'); if (!ta) return;
  S.lastQuery = ta.value;
  const out = $('#qres');
  try {
    const env = run(ta.value);
    const cell = (v) => (v && typeof v === 'object' ? JSON.stringify(v, (k, x) => (k === 'item_vec' ? undefined : x)) : v ?? '');
    $('#qmeta').textContent = `${env.rows.length} row${env.rows.length === 1 ? '' : 's'} · ${fmtMs(env.elapsed_ms)} in Relate (WebAssembly)`;
    out.innerHTML = env.rows.length ? `<table class="res"><thead><tr>${env.columns.map((c) => `<th>${esc(c)}</th>`).join('')}</tr></thead>
      <tbody>${env.rows.slice(0, 100).map((r) => `<tr>${env.columns.map((c) => `<td>${esc(cell(r[c]))}</td>`).join('')}</tr>`).join('')}</tbody></table>` : '<p class="q-why">No rows.</p>';
  } catch (e) {
    $('#qmeta').textContent = 'error';
    out.innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
}

// ---------------------------------------------------------------- actions
function select(id, animate = true) {
  if (!S.invoices.find((i) => i.id === id)) id = 'INV-1042';
  S.sel = id;
  if (location.hash.slice(1) !== id) history.replaceState(null, '', '#' + id);
  renderLedger();
  renderStage(animate);
}

function linkReceipt(grn, po) {
  const at = new Date().toISOString().slice(0, 19) + 'Z';
  const env = run(S.Q.link_receipt.text, { grn, po, by: 'browser', note: 'linked from the trail view', at });
  if (!env.rows.length) return;
  const inv = S.sel;
  S.linked.set(grn, { po, was: env.rows[0].was_keyed_as, invoice: inv });
  scan();
  renderLedger();
  renderStage(false);
  const st = $('#status'); st.animate([{ transform: 'scale(1.08)' }, { transform: 'none' }], { duration: 420, easing: 'ease-out' });
}

function reset() {
  S.linked.clear();
  loadGraph(); scan(); select(S.sel);
}

document.addEventListener('click', (e) => {
  const row = e.target.closest('[data-inv]'); if (row) return select(row.dataset.inv);
  const l = e.target.closest('[data-link]'); if (l) { const [g, p] = l.dataset.link.split('|'); return linkReceipt(g, p); }
  const t = e.target.closest('[data-tab]'); if (t) { S.tab = t.dataset.tab; return renderSide(explain(S.sel)); }
  const p = e.target.closest('[data-preset]'); if (p) { $('#cq').value = PRESETS[+p.dataset.preset][1]; return runConsole(); }
  if (e.target.closest('#runq')) return runConsole();
  if (e.target.closest('[data-reset]')) return reset();
  if (e.target.closest('[data-rewalk]')) return walk(S.ex);
});
document.getElementById('how-open').addEventListener('click', () => document.getElementById('how').showModal());
document.getElementById('how').addEventListener('click', (e) => {
  if (e.target.closest('[data-close]') || e.target.id === 'how') document.getElementById('how').close();
});
document.addEventListener('keydown', (e) => { if (e.target.id === 'cq' && e.key === 'Enter' && (e.ctrlKey || e.metaKey)) runConsole(); });
document.addEventListener('mouseover', (e) => {
  if (DRAG) return;
  const k = e.target.closest('svg.trail .card[data-id]');
  if (k) return lightUp(k.dataset.id);
  if (e.target.closest('svg.trail')) return lightUp(null);
  const c = e.target.closest('.chip'); if (!c) return;
  lightUp(c.dataset.id);
  document.querySelectorAll(`svg .card[data-id="${c.dataset.id}"]`).forEach((g) => g.classList.add('focus'));
});
document.addEventListener('mouseout', (e) => {
  if (e.target.closest('svg.trail') && !e.relatedTarget?.closest?.('svg.trail')) lightUp(null);
  const c = e.target.closest('.chip'); if (!c) return;
  lightUp(null);
  document.querySelectorAll(`svg .card[data-id="${c.dataset.id}"]`).forEach((g) => { if (g.dataset.id !== S.sel) g.classList.remove('focus'); });
});
window.addEventListener('hashchange', () => { const id = location.hash.slice(1); if (id && id !== S.sel) select(id); });

// ---------------------------------------------------------------- boot
async function boot() {
  const eng = $('#engine');
  try {
    const t0 = performance.now();
    const [, graph, Q] = await Promise.all([init(), fetch('data/graph.json').then((r) => r.json()), fetch('data/queries.json').then((r) => r.json())]);
    S.graph = graph; S.Q = Q;
    const t1 = performance.now();
    loadGraph();
    scan();
    const n = graph.nodes.reduce((a, g) => a + g.rows.length, 0), r = graph.rels.reduce((a, g) => a + g.rows.length, 0);
    eng.classList.add('ready');
    eng.innerHTML = `<span class="pulse"></span>Relate 1.0.1 · WebAssembly · <b>${n}</b> nodes · <b>${r}</b> rels · built in ${Math.round(performance.now() - t1)} ms`;
    select(location.hash.slice(1) || 'INV-1042');
    const ap = new URLSearchParams(location.search).get('apply');
    if (ap) { const [g, p] = ap.split(','); linkReceipt(g, p); }
  } catch (err) {
    console.error(err);
    eng.classList.add('fail');
    eng.innerHTML = '<span class="pulse"></span>Engine failed to start';
    $('#stage').innerHTML = `<div class="loading"><p>Could not start the graph engine: <code>${esc(err.message)}</code></p><p>Open this page through <code>python -m trailmark view</code> (or the hosted demo), not as a file.</p></div>`;
  }
}
boot();
