// Browser tests for the demo story. Start the app first (start-demo.bat), then: npm install && npm test
// Uses the Edge or Chrome already installed on the machine. Override with E2E_BROWSER=<path to browser>.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readdirSync } from 'node:fs';
import { chromium } from 'playwright-core';

const BASE = process.env.BASE_URL ?? 'http://localhost:8080';
const PASSWORD = process.env.CALLVERSE_DEMO_PASSWORD ?? 'demo-password-123';

function findBrowser() {
  if (process.env.E2E_BROWSER) return process.env.E2E_BROWSER;
  const fixed = [
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  ].find(existsSync);
  if (fixed) return fixed;
  const core = 'C:/Program Files (x86)/Microsoft/EdgeCore';
  if (existsSync(core)) {
    const v = readdirSync(core).sort().reverse().find((d) => existsSync(`${core}/${d}/msedge.exe`));
    if (v) return `${core}/${v}/msedge.exe`;
  }
  throw new Error('No Edge or Chrome found. Set E2E_BROWSER to the browser path.');
}

let browser;
before(async () => { browser = await chromium.launch({ executablePath: findBrowser(), headless: true }); });
after(async () => { await browser?.close(); });

async function signIn(user, viewport = { width: 1440, height: 900 }) {
  const ctx = await browser.newContext({ viewport, reducedMotion: 'reduce' });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login`);
  await page.fill('#username', user);
  await page.fill('#password', PASSWORD);
  await page.click('button[type=submit]');
  await page.waitForURL(`${BASE}/`);
  return { ctx, page };
}

test('a wrong password is refused', async () => {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login`);
  await page.fill('#username', 'admin');
  await page.fill('#password', 'not-the-password');
  await page.click('button[type=submit]');
  await page.waitForURL(/error/);
  assert.match(await page.textContent('.alert'), /Wrong username or password/);
  await ctx.close();
});

test('the client can play a full call and it ends resolved', async () => {
  const { ctx, page } = await signIn('yasmine');
  await page.goto(`${BASE}/client?persona=IMPATIENT&memory=true`);
  for (const label of ['Acknowledge the frustration', 'Check the refund policy', 'Confirm the fix in writing']) {
    await page.click(`.choice:has-text("${label}")`);
    await page.waitForLoadState();
  }
  assert.match(await page.textContent('.outcome h3'), /Resolved/);
  // the finished call is remembered in this browser
  await page.goto(`${BASE}/client`);
  assert.equal(await page.locator('#history-list li').count(), 1);
  await ctx.close();
});

test('a role only sees its own workspace', async () => {
  const { ctx, page } = await signIn('karim');
  const res = await page.goto(`${BASE}/workforce`);
  assert.equal(res.status(), 403);
  assert.equal((await page.goto(`${BASE}/advisor`)).status(), 200);
  await ctx.close();
});

test('the command palette finds a page and opens it', async () => {
  const { ctx, page } = await signIn('admin');
  await page.keyboard.press('Control+K');
  await page.fill('dialog.palette input', 'quality');
  await page.keyboard.press('Enter');
  await page.waitForURL(`${BASE}/quality`);
  await ctx.close();
});

test('dark mode toggles and is remembered', async () => {
  const { ctx, page } = await signIn('admin');
  await page.click('.theme-toggle');
  assert.equal(await page.getAttribute('html', 'data-theme'), 'dark');
  await page.reload();
  assert.equal(await page.getAttribute('html', 'data-theme'), 'dark');
  await ctx.close();
});

test('the demo tour walks from the home page to the simulator', async () => {
  const { ctx, page } = await signIn('admin');
  await page.click('[data-tour="start"]');
  assert.match(await page.textContent('.tour h2'), /Welcome/);
  await page.click('.tour .btn');
  await page.waitForURL(`${BASE}/client`);
  assert.match(await page.textContent('.tour h2'), /Yasmine/);
  await page.click('.tour .btn-quiet:has-text("End tour")');
  assert.equal(await page.locator('.tour').count(), 0);
  await ctx.close();
});

test('escalating a complaint moves it up a lane and updates the counts', async () => {
  const { ctx, page } = await signIn('admin');
  await page.goto(`${BASE}/complaints`);
  const high = page.locator('.lane[data-lane="high"]');
  await high.locator('[data-escalate]').click();
  assert.equal(await page.locator('.lane[data-lane="critical"] .case').count(), 2);
  assert.equal((await high.locator('.count').textContent()).trim(), '0');
  await ctx.close();
});

test('presentation mode steps with the keys and shows speaker notes', async () => {
  const { ctx, page } = await signIn('admin');
  await page.goto(`${BASE}/present`);
  assert.equal((await page.textContent('#pcount')).trim(), '1 / 14');
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');
  assert.equal((await page.textContent('#pcount')).trim(), '3 / 14');
  await page.keyboard.press('n');
  assert.ok((await page.textContent('#notes')).length > 20);
  await ctx.close();
});

test('no page scrolls sideways on a phone', async () => {
  const { ctx, page } = await signIn('admin', { width: 390, height: 844 });
  for (const path of ['/', '/client', '/advisor', '/workforce', '/quality', '/complaints', '/training', '/sales', '/personas', '/ideas', '/insights', '/pipeline']) {
    await page.goto(`${BASE}${path}`);
    await page.waitForLoadState('networkidle');
    const over = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    assert.ok(over <= 1, `${path} overflows by ${over}px`);
  }
  await ctx.close();
});

test('the training builder adds a scenario and what-if compares one change', async () => {
  const { ctx, page } = await signIn('admin');
  await page.goto(`${BASE}/training`);
  await page.selectOption('#gen-diff', 'Hard');
  await page.click('#generate');
  assert.equal(await page.locator('#scenarios .scn').count(), 4);
  assert.match(await page.textContent('#scenarios .scn:first-child .chips'), /Hard/);
  await page.click('#scenarios .scn:first-child [data-act="whatif"]');
  assert.equal(await page.locator('#whatif').isVisible(), true);
  assert.ok((await page.textContent('#wi-note')).length > 20);
  await ctx.close();
});

test('the workforce slider moves the marker and the quality pins show the evidence', async () => {
  const { ctx, page } = await signIn('admin');
  await page.goto(`${BASE}/workforce`);
  assert.match(await page.textContent('#scrub-read'), /forecast 72 calls\/h/); // starts on the peak hour
  await page.fill('#hour', '0');
  assert.match(await page.textContent('#scrub-read'), /^9h: forecast 22/);
  await page.goto(`${BASE}/quality`);
  const first = page.locator('.review').first();
  await first.locator('.pin').first().click();
  assert.match(await first.locator('.pin-read').textContent(), /Accuracy/);
  await ctx.close();
});

test('the ideas filter hides the other decisions', async () => {
  const { ctx, page } = await signIn('admin');
  await page.goto(`${BASE}/ideas`);
  await page.click('[data-filter="perspective"]');
  assert.equal(await page.locator('.idea:visible').count(), 4);
  assert.equal(await page.getAttribute('[data-filter="perspective"]', 'aria-pressed'), 'true');
  await ctx.close();
});

test('customer insights: filters change the numbers, small groups stay hidden, the sidebar link works', async () => {
  const { ctx, page } = await signIn('admin');
  await page.click('.sidebar a[href="/insights"]');
  await page.waitForURL(`${BASE}/insights`);
  assert.equal(await page.locator('.ibars').count() >= 4, true);       // 3 charts + the fairness charts
  const all = (await page.textContent('.stat strong')).trim();
  assert.equal(all, '720');
  await page.selectOption('#f-age', '18-25');
  await page.selectOption('#f-metric', 'wait');
  await page.click('.insight-form button[type=submit]');
  await page.waitForURL(/age=18-25/);
  assert.notEqual((await page.textContent('.stat strong')).trim(), all);
  assert.match(await page.textContent('h2[id^="ch-"]'), /Average wait/);
  await page.goto(`${BASE}/insights?age=51%2B&sex=Female&region=Nabeul`);
  assert.match(await page.textContent('main'), /Fewer than 10 customers/);
  await ctx.close();
});
