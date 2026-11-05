// Audit: accessibility (axe-core), console errors, failed requests, on every page, light and dark. Usage: node audit.mjs
import { chromium } from 'playwright-core';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
const BASE = process.env.BASE_URL ?? 'http://localhost:8080', PASSWORD = process.env.CALLVERSE_DEMO_PASSWORD ?? 'demo-password-123';
const core = 'C:/Program Files (x86)/Microsoft/EdgeCore';
const v = readdirSync(core).sort().reverse().find((d) => existsSync(`${core}/${d}/msedge.exe`));
const axe = readFileSync('node_modules/axe-core/axe.min.js', 'utf8');
const pages = ['/', '/client', '/client?persona=ANGRY_PREMIUM&moves=EMPATHY,ASK_REPEAT', '/client?moves=EMPATHY,CHECK_POLICY,FOLLOW_UP', '/advisor', '/workforce', '/quality', '/complaints', '/complaints/CMP-221', '/training', '/sales', '/personas', '/ideas', '/insights', '/pipeline', '/present'];
const b = await chromium.launch({ executablePath: `${core}/${v}/msedge.exe` });
const found = new Map();
for (const scheme of ['light', 'dark']) {
  const ctx = await b.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce', colorScheme: scheme, bypassCSP: true });
  const p = await ctx.newPage();
  const problems = [];
  p.on('console', (m) => { if (['error', 'warning'].includes(m.type())) problems.push(`console ${m.type()}: ${m.text().slice(0, 140)}`); });
  p.on('pageerror', (e) => problems.push(`pageerror: ${e.message.slice(0, 140)}`));
  p.on('response', (r) => { if (r.status() >= 400) problems.push(`HTTP ${r.status()} ${r.url().replace(BASE, '')}`); });
  await p.goto(`${BASE}/login`); await p.fill('#username', 'admin'); await p.fill('#password', PASSWORD); await p.click('button[type=submit]'); await p.waitForURL(`${BASE}/`);
  for (const path of pages) {
    problems.length = 0;
    await p.goto(BASE + path); await p.waitForLoadState('networkidle'); await p.waitForTimeout(300);
    await p.addScriptTag({ content: axe });
    const res = await p.evaluate(async () => (await window.axe.run(document, { resultTypes: ['violations'] })).violations.map((x) => ({ id: x.id, impact: x.impact, n: x.nodes.length, help: x.help, sample: x.nodes[0].target.join(' '), html: x.nodes[0].html.slice(0, 110) })));
    for (const r of res) found.set(`${scheme} ${path} ${r.id}`, `[${r.impact}] ${r.help} (${r.n}x) e.g. ${r.sample} -> ${r.html}`);
    for (const m of problems) found.set(`${scheme} ${path} ${m}`, m);
  }
  await ctx.close();
}
await b.close();
console.log(found.size === 0 ? 'NO PROBLEMS FOUND' : `${found.size} findings:`);
for (const [k, val] of found) console.log('-', k.split(' ').slice(0, 2).join(' '), '|', val);
