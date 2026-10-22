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

test('escalating a complaint moves it up a lane and updates the counts', async (t) => {
  const { ctx, page } = await signIn('admin');
  await page.goto(`${BASE}/complaints`);
  if ((await page.locator('.lane[data-lane]').count()) === 0) { await ctx.close(); return t.skip('the real complaint agent is running: see the test after this one'); }
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
  // the numbers come from whichever agent is behind the page (demo data or the Python agent), so read them from the chart itself
  const points = await page.$$eval('[data-forecast]', (els) => els.map((e) => ({ hour: e.dataset.hour, forecast: Number(e.dataset.forecast) })));
  const peak = Math.max(...points.map((p) => p.forecast));
  assert.match(await page.textContent('#scrub-read'), new RegExp(`forecast ${peak} calls/h`)); // starts on the peak hour
  await page.fill('#hour', '0');
  assert.match(await page.textContent('#scrub-read'), new RegExp(`^9h: forecast ${points[0].forecast}`));
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

test('the client can be played by typing replies, and the app shows how each was read', async () => {
  const { ctx, page } = await signIn('yasmine');
  await page.goto(`${BASE}/client?persona=IMPATIENT&memory=true`);
  for (const text of ["I'm so sorry, I understand how frustrating this is.", 'Let me check the refund policy first.', "I'll send you a confirmation by email."]) {
    await page.fill('#reply', text);
    await page.click('.say button');
    await page.waitForLoadState();
  }
  assert.equal(await page.locator('.read-as').count(), 3);
  assert.match(await page.textContent('.read-as >> nth=1'), /check the refund policy/);
  assert.match(await page.textContent('.outcome h3'), /Resolved/);
  await ctx.close();
});

test('every sidebar link is visible without scrolling the rail on common laptop heights', async () => {
  for (const height of [650, 720, 768, 900]) {
    const { ctx, page } = await signIn('admin', { width: 1280, height });
    const hidden = await page.evaluate(() => { const s = document.querySelector('.nav-scroll'); return s.scrollHeight - s.clientHeight; });
    assert.ok(hidden <= 1, `at ${height}px high, the rail hides ${hidden}px of links`);
    await ctx.close();
  }
});

test('the whole app has no accessibility violations (axe-core) and no console errors', async () => {
  const { execFileSync } = await import('node:child_process');
  const out = execFileSync('node', ['audit.mjs'], { encoding: 'utf8', cwd: import.meta.dirname, timeout: 240000 });
  assert.match(out, /NO PROBLEMS FOUND/, out);
});

test('particles: on by default, the sidebar button turns them off, and the choice is remembered', async () => {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } }); // motion allowed
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login`);
  await page.fill('#username', 'admin'); await page.fill('#password', PASSWORD); await page.click('button[type=submit]');
  await page.waitForURL(`${BASE}/`);
  assert.equal(await page.locator('canvas.fx').count(), 1);
  // it really draws something, and never blocks clicks
  assert.equal(await page.evaluate(() => getComputedStyle(document.querySelector('canvas.fx')).pointerEvents), 'none');
  await page.waitForTimeout(400);
  assert.equal(await page.evaluate(() => { const c = document.querySelector('canvas.fx'); return c.getContext('2d').getImageData(0, 0, c.width, c.height).data.some((v) => v > 0); }), true);
  await page.click('.fx-toggle');
  assert.equal(await page.locator('canvas.fx').count(), 0);
  assert.equal(await page.getAttribute('.fx-toggle', 'aria-pressed'), 'false');
  await page.reload();
  assert.equal(await page.locator('canvas.fx').count(), 0);
  await ctx.close();
});

test('particles stay off for people who ask for reduced motion', async () => {
  const { ctx, page } = await signIn('admin'); // signIn() uses reduced motion
  assert.equal(await page.locator('canvas.fx').count(), 0);
  await ctx.close();
});

test('in the expanded sidebar a hovered name stays level with its icon', async () => {
  const { ctx, page } = await signIn('admin', { width: 1280, height: 900 });
  await page.click('.nav-toggle');
  await page.waitForTimeout(700);
  for (const href of ['/advisor', '/quality', '/ideas']) {
    const link = page.locator(`.sidebar a.nav[href="${href}"]`);
    await link.hover();
    await page.waitForTimeout(450);
    const off = await link.evaluate((el) => { const l = el.querySelector('.nav-label').getBoundingClientRect(), i = el.querySelector('.ico').getBoundingClientRect(); return (l.top + l.height / 2) - (i.top + i.height / 2); });
    assert.ok(Math.abs(off) <= 3, `${href}: the name is ${off}px off its icon while hovered`);
  }
  await ctx.close();
});

test('collapsed sidebar on a short window: the hover name is visible, level with its icon and above the page', async () => {
  const { ctx, page } = await signIn('admin', { width: 1280, height: 720 });
  const link = page.locator('.sidebar a.nav[href="/advisor"]');
  await link.hover();
  await page.waitForTimeout(500);
  const r = await link.evaluate((el) => {
    const lab = el.querySelector('.nav-label'), l = lab.getBoundingClientRect(), i = el.querySelector('.ico').getBoundingClientRect();
    const rail = lab.closest('.nav-scroll');
    return { opacity: getComputedStyle(lab).opacity, off: (l.top + l.height / 2) - (i.top + i.height / 2), clipped: getComputedStyle(rail).overflowY !== 'visible',
             z: Number(getComputedStyle(document.querySelector('.sidebar')).zIndex) };
  });
  assert.equal(r.opacity, '1');
  assert.ok(Math.abs(r.off) <= 3, `the name is ${r.off}px off its icon`);
  assert.equal(r.clipped, false, 'the rail must not clip the hover names');
  assert.ok(r.z >= 40, 'the sidebar must sit above the page cards');
  await ctx.close();
});

test('sidebar names move a little on hover (a nudge when expanded, a slide-out when collapsed) and stay level with the icon', async () => {
  const { ctx, page } = await signIn('admin', { width: 1280, height: 800 });
  const link = page.locator('.sidebar a.nav[href="/quality"]');
  const x = () => link.evaluate((el) => el.querySelector('.nav-label').getBoundingClientRect().left);
  // collapsed: the name slides out from the icon
  const hidden = await x();
  await link.hover(); await page.waitForTimeout(600);
  assert.ok((await x()) - hidden >= 8, 'the collapsed name should slide out by at least 8px');
  // expanded: the name nudges to the right
  await page.click('.nav-toggle'); await page.waitForTimeout(700);
  await page.mouse.move(700, 400); await page.waitForTimeout(500);
  const rest = await x();
  await link.hover(); await page.waitForTimeout(600);
  const moved = (await x()) - rest;
  assert.ok(moved >= 4 && moved <= 10, `the expanded name should nudge 4 to 10px, it moved ${moved}px`);
  await ctx.close();
});

test('polish: the real font loads, below-fold cards fade up and settle, numbers count up to the right value', async () => {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 700 } }); // motion allowed
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login`);
  await page.fill('#username', 'admin'); await page.fill('#password', PASSWORD); await page.click('button[type=submit]');
  await page.waitForURL(`${BASE}/`);
  await page.waitForTimeout(400);
  assert.equal(await page.evaluate(async () => { await document.fonts.ready; return document.fonts.check('600 16px "Plus Jakarta Sans"') && [...document.fonts].some((f) => f.family.includes('Plus Jakarta') && f.status === 'loaded'); }), true, 'the bundled font should be loaded');

  // insights has panels well below the first screen
  await page.goto(`${BASE}/insights`);
  await page.waitForTimeout(500);
  assert.ok(await page.locator('.pre').count() > 0, 'cards below the fold should wait to be revealed');
  const handle = await page.locator('.pre').first().elementHandle();
  await handle.scrollIntoViewIfNeeded();
  await page.waitForTimeout(2200);
  assert.equal(await handle.evaluate((el) => el.classList.contains('pre') || el.classList.contains('in')), false, 'a revealed card must return to normal (no leftover classes)');
  assert.equal(await handle.evaluate((el) => getComputedStyle(el).opacity), '1', 'no flicker after the reveal');
  await page.waitForTimeout(1200);
  assert.equal(await handle.evaluate((el) => getComputedStyle(el).opacity), '1', 'still fully visible a second later');
  // count-up ends on the real number
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(1500);
  assert.equal((await page.textContent('.stat strong')).trim(), '720');
  await ctx.close();
});

test('pressing ? opens the keyboard shortcuts window and Esc closes it; typing a ? in a field does not', async () => {
  const { ctx, page } = await signIn('admin');
  await page.keyboard.press('?');
  assert.equal(await page.locator('dialog.shortcuts[open]').count(), 1);
  assert.match(await page.textContent('dialog.shortcuts'), /Jump to any page/);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('dialog.shortcuts[open]').count(), 0);
  await page.goto(`${BASE}/advisor`);                       // the search box is a text field
  await page.fill('#q', 'what');
  await page.press('#q', '?');
  assert.equal(await page.locator('dialog.shortcuts[open]').count(), 0);
  assert.ok((await page.inputValue('#q')).endsWith('?'));
  await ctx.close();
});

test('switching the theme cross-fades, and an unknown page shows the friendly error with a way home', async () => {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } }); // motion allowed
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login`);
  await page.fill('#username', 'admin'); await page.fill('#password', PASSWORD); await page.click('button[type=submit]');
  await page.waitForURL(`${BASE}/`);
  await page.click('.theme-toggle');
  assert.equal(await page.evaluate(() => document.documentElement.classList.contains('theme-fade')), true, 'the fade class is set during the change');
  await page.waitForTimeout(800);
  assert.equal(await page.evaluate(() => document.documentElement.classList.contains('theme-fade')), false, 'and removed afterwards');
  const res = await page.goto(`${BASE}/definitely-not-here`);
  assert.equal(res.status(), 404);
  assert.match(await page.textContent('main'), /find that page/);
  await page.click('text=Back to orqestra');
  await page.waitForURL(`${BASE}/`);
  await ctx.close();
});

test('agents speak: answers have a Listen button and the live call reads the customer aloud, shaped by her mood', async () => {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  await ctx.addInitScript(() => {   // a recording stand-in for the browser's speech, so the test needs no sound card
    window.__said = [];
    Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: {
      speak: (u) => { window.__said.push({ text: u.text, rate: u.rate, pitch: u.pitch }); setTimeout(() => u.onend && u.onend(), 5); },
      cancel() {}, getVoices: () => [] } });
    window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
  });
  const page = await ctx.newPage();
  await page.route('**/voice/speak', (r) => r.fulfill({ status: 503, contentType: 'application/json', body: '{}' }));   // no neural voice: the browser voice takes over
  await page.goto(`${BASE}/login`);
  await page.fill('#username', 'karim'); await page.fill('#password', PASSWORD); await page.click('button[type=submit]');
  await page.waitForURL(`${BASE}/`);
  await page.goto(`${BASE}/advisor`);

  await page.locator('.answer .listen').first().click();
  const answer = (await page.locator('.answer p[data-speak]').first().textContent()).trim();
  assert.equal((await page.evaluate(() => window.__said))[0].text.replace(/\s+/g, ' ').trim(), answer.replace(/\s+/g, ' '));

  await page.selectOption('#lv-persona', 'ANGRY_PREMIUM');
  await page.click('#live-setup button[type=submit]');
  await page.waitForSelector('#live-call:not([hidden])');
  const said = await page.evaluate(() => window.__said);
  const opening = said.at(-1);
  assert.match(opening.text, /charged twice/);
  assert.ok(opening.pitch > 1 && opening.rate > 1, 'an upset customer sounds faster and higher');

  await page.uncheck('#lv-voice'); await page.uncheck('#lv-sayme');
  const before = (await page.evaluate(() => window.__said)).length;
  await page.fill('#lv-text', 'I am so sorry, I understand.');
  await page.click('#live-say button[type=submit]');
  await page.waitForFunction(() => document.querySelectorAll('#live-log li').length >= 3);
  assert.equal((await page.evaluate(() => window.__said)).length, before, 'voice off: nothing is spoken');
  await ctx.close();
});

test('neural voice: the customer is read sentence by sentence in her own voice, shaped by her mood', async () => {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  const page = await ctx.newPage();
  const wav = Buffer.concat([Buffer.from('RIFF'), Buffer.from([36, 0, 0, 0]), Buffer.from('WAVEfmt '), Buffer.from([16, 0, 0, 0, 1, 0, 1, 0, 0x40, 0x1f, 0, 0, 0x80, 0x3e, 0, 0, 2, 0, 16, 0]), Buffer.from('data'), Buffer.from([0, 0, 0, 0])]);
  const asked = [];
  await page.route('**/voice/speak', (r) => { asked.push(JSON.parse(r.request().postData())); r.fulfill({ status: 200, contentType: 'audio/wav', body: wav }); });
  await page.goto(`${BASE}/login`);
  await page.fill('#username', 'karim'); await page.fill('#password', PASSWORD); await page.click('button[type=submit]');
  await page.waitForURL(`${BASE}/`);
  await page.goto(`${BASE}/advisor`);
  await page.selectOption('#lv-persona', 'ANGRY_PREMIUM');
  await page.click('#live-setup button[type=submit]');
  await page.waitForSelector('#live-call:not([hidden])');
  await page.waitForFunction(() => true);
  await page.waitForTimeout(500);
  assert.ok(asked.length >= 1, 'the opening line was sent to the neural voice');
  assert.deepEqual({ role: asked[0].role, persona: asked[0].persona, mood: asked[0].mood }, { role: 'customer', persona: 'ANGRY_PREMIUM', mood: 35 });
  assert.match(asked[0].text, /charged twice/);
  await ctx.close();
});

test('a typed reply is also said aloud in the advisor voice, before the customer answers', async () => {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  await ctx.addInitScript(() => {
    window.__said = [];
    Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: {
      speak: (u) => { window.__said.push(u.text); setTimeout(() => u.onend && u.onend(), 5); }, cancel() {}, getVoices: () => [] } });
    window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
  });
  const page = await ctx.newPage();
  await page.route('**/voice/speak', (r) => r.fulfill({ status: 503, contentType: 'application/json', body: '{}' }));
  await page.goto(`${BASE}/login`);
  await page.fill('#username', 'karim'); await page.fill('#password', PASSWORD); await page.click('button[type=submit]');
  await page.waitForURL(`${BASE}/`);
  await page.goto(`${BASE}/advisor`);
  await page.click('#live-setup button[type=submit]');
  await page.waitForSelector('#live-call:not([hidden])');
  await page.fill('#lv-text', 'I am so sorry, I understand how frustrating this is.');
  await page.click('#live-say button[type=submit]');
  await page.waitForFunction(() => window.__said.length >= 3);
  const said = await page.evaluate(() => window.__said);
  assert.match(said[1], /so sorry/, 'the advisor is heard first');
  assert.ok(said[2] && said[2] !== said[1], 'then the customer answers');
  assert.equal(await page.locator('#live-log .advisor button.listen').count(), 1, 'a typed reply has its own Listen button');
  await ctx.close();
});

test('voice notes: the advisor records, the speech-to-text agent writes it down, the customer answers', async () => {
  const mic = await chromium.launch({ executablePath: findBrowser(), headless: true, args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
  try {
    const ctx = await mic.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', permissions: ['microphone'] });
    const page = await ctx.newPage();
    let received = 0;
    await page.route('**/voice/speak', (r) => r.fulfill({ status: 503, contentType: 'application/json', body: '{}' }));
    await page.route('**/voice/transcribe', (r) => {
      received = r.request().postDataBuffer().length;
      assert.equal(r.request().headers()['content-type'], 'audio/wav');
      r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ text: 'I will check the refund policy first.', seconds: 1.5 }) });
    });
    await page.goto(`${BASE}/login`);
    await page.fill('#username', 'karim'); await page.fill('#password', PASSWORD); await page.click('button[type=submit]');
    await page.waitForURL(`${BASE}/`);
    await page.goto(`${BASE}/advisor`);
    await page.click('#live-setup button[type=submit]');
    await page.waitForSelector('#live-call:not([hidden])');
    await page.click('#lv-rec');
    await page.waitForFunction(() => document.getElementById('lv-rec').classList.contains('recording'));
    await page.waitForTimeout(1500);
    await page.click('#lv-rec');
    await page.waitForFunction(() => document.querySelectorAll('#live-log li').length >= 3, null, { timeout: 20000 });
    assert.ok(received > 1000, 'a WAV recording was sent');
    assert.equal(await page.locator('#live-log li audio').count(), 1, 'the voice note stays playable in the call');
    assert.match(await page.locator('#live-log li.advisor').innerText(), /refund policy first/);
    assert.match(await page.locator('#live-log li.client').last().innerText(), /Check the refund policy/);
    assert.equal(await page.textContent('#lv-rec'), 'Record voice note');
    await ctx.close();
  } finally { await mic.close(); }
});

test('voice notes fail kindly: no speech model means a message and typing still works', async () => {
  const mic = await chromium.launch({ executablePath: findBrowser(), headless: true, args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
  try {
    const ctx = await mic.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', permissions: ['microphone'] });
    const page = await ctx.newPage();
    await page.route('**/voice/speak', (r) => r.fulfill({ status: 503, contentType: 'application/json', body: '{}' }));
    await page.route('**/voice/transcribe', (r) => r.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'Voice notes need the speech-to-text model. You can type instead.' }) }));
    await page.goto(`${BASE}/login`);
    await page.fill('#username', 'karim'); await page.fill('#password', PASSWORD); await page.click('button[type=submit]');
    await page.waitForURL(`${BASE}/`);
    await page.goto(`${BASE}/advisor`);
    await page.click('#live-setup button[type=submit]');
    await page.waitForSelector('#live-call:not([hidden])');
    await page.click('#lv-rec');
    await page.waitForFunction(() => document.getElementById('lv-rec').classList.contains('recording'));
    await page.waitForTimeout(800);
    await page.click('#lv-rec');
    await page.waitForFunction(() => /You can type instead/.test(document.getElementById('live-status').textContent), null, { timeout: 15000 });
    assert.equal(await page.isEnabled('#live-say button[type=submit]'), true);
    assert.equal(await page.isEnabled('#lv-rec'), true);
    await ctx.close();
  } finally { await mic.close(); }
});

test('workforce routing: a plan with moves and its explanation, readable aloud', async () => {
  const { ctx, page } = await signIn('sana');
  await page.goto(`${BASE}/workforce`);
  const sec = page.locator('section[aria-labelledby=rt]');
  assert.match(await sec.locator('p.result').innerText(), /Calls answered within 20 s: \d+% becomes \d+%/);
  assert.ok(await sec.locator('ol li').count() >= 1, 'at least one move');
  assert.ok(await sec.locator('ol li .listen').count() >= 1, 'a move can be listened to');
  await sec.locator('details').first().locator('summary').click();
  assert.equal(await sec.locator('details').first().locator('tbody tr:visible').count(), 5, 'all five queues are listed');
  await sec.locator('button[data-toast]').click();
  assert.match(await page.locator('.toast').first().innerText(), /nothing was changed/);
  await ctx.close();
});

test('workforce breaks and shifts: a lunch plan per queue and the overtime still needed', async () => {
  const { ctx, page } = await signIn('sana');
  await page.goto(`${BASE}/workforce`);
  const sec = page.locator('section[aria-labelledby=breaks]');
  assert.match(await sec.locator('p.result').innerText(), /Everybody at noon: \d+% of calls answered within 20 s\. Lunches spread out: \d+%/);
  assert.equal(await sec.locator('table tbody tr:visible').count(), 5, 'all five queues');
  assert.ok(await sec.locator('table thead th').count() >= 7, 'one column per lunch hour');
  await ctx.close();
});

// ---- quality analyst: these need the real Python agents (skipped when they are not running) ----
async function agentsUp() {
  try { const r = await fetch('http://localhost:8000/health'); return r.ok ? await r.json() : null; } catch { return null; }
}

test('quality: the page shows team analytics, advisors with a coaching plan, and reviews with a transcript', async () => {
  const { ctx, page } = await signIn('nour');
  await page.goto(`${BASE}/quality`);
  assert.ok(await page.locator('#qa').count(), 'team analytics');
  assert.ok(await page.locator('table.advisors tbody tr').count() >= 1, 'at least one advisor');
  await page.locator('table.advisors details summary').first().click();
  assert.ok((await page.locator('table.advisors .plan li').first().innerText()).length > 20, 'a coaching plan is written out');
  assert.ok(await page.locator('article.review').count() >= 2, 'reviews');
  assert.ok(await page.locator('article.review .listen').count() >= 1, 'coaching can be listened to');
  await ctx.close();
});

test('quality: a live call sent by the advisor shows up as a review for Nour', async (t) => {
  if (!(await agentsUp())) return t.skip('the Python agents are not running');
  const karim = await signIn('karim');
  await karim.page.goto(`${BASE}/advisor`);
  await karim.page.uncheck('#lv-voice'); await karim.page.uncheck('#lv-sayme');
  await karim.page.click('#live-setup button[type=submit]');
  await karim.page.waitForSelector('#live-call:not([hidden])');
  await karim.page.fill('#lv-text', 'I will refund you right away.');
  await karim.page.click('#live-say button[type=submit]');
  await karim.page.waitForFunction(() => document.querySelectorAll('#live-log li').length >= 3);
  await karim.page.click('#lv-review');
  await karim.page.waitForFunction(() => /Sent: CALL-\d+ scored \d+\/100/.test(document.getElementById('live-status').textContent), null, { timeout: 30000 });
  const id = /Sent: (CALL-\d+)/.exec(await karim.page.textContent('#live-status'))[1];
  await karim.ctx.close();

  const nour = await signIn('nour');
  await nour.page.goto(`${BASE}/quality?call=${id}`);
  const card = nour.page.locator(`article#${id}`);
  assert.equal(await card.count(), 1);
  assert.match(await card.innerText(), /live call/);
  assert.equal(await nour.page.locator('article.review').first().getAttribute('id'), id, 'the focused call comes first');
  const drivers = card.locator('.drivers');
  assert.match(await drivers.innerText(), /Lowered the score/);
  assert.match(await drivers.locator('.driver-list li', { hasText: 'Promised a refund before checking' }).first().innerText(), /^−\d+/, 'its cost on the score');
  assert.match(await drivers.locator('.driver-list li', { hasText: 'Promised a refund before checking' }).first().locator('q').innerText(), /refund you right away/);
  await card.locator('summary', { hasText: 'points were lost' }).click();
  assert.match(await card.locator('.lost').first().innerText(), /Promised a refund before checking/);
  await card.locator('summary', { hasText: 'Transcript' }).click();
  assert.match(await card.locator('.transcript').innerText(), /I will refund you right away\./);
  await nour.ctx.close();
});

test('quality: a two-channel recording is uploaded, transcribed by speaker, and its review opens', async (t) => {
  const h = await agentsUp();
  if (!h || !h.listen || !h.voice) return t.skip('the Python agents or the voice models are not available');
  const { ctx, page } = await signIn('nour');
  await page.goto(`${BASE}/quality`);
  const sample = await page.request.get(`${BASE}/quality/sample-call.wav`, { timeout: 180000 });
  assert.equal(sample.status(), 200);
  await page.setInputFiles('#rec-file', { name: 'call.wav', mimeType: 'audio/wav', buffer: await sample.body() });
  await page.fill('#rec-advisor', 'Karim B.');
  await page.click('#audio-form button[type=submit]');
  await page.waitForURL(/\/quality\?call=CALL-\d+/, { timeout: 180000 });
  const card = page.locator('article.review.focus');
  assert.match(await card.innerText(), /recording/);
  await card.locator('summary', { hasText: 'Transcript' }).click();
  const text = await card.locator('.transcript').innerText();
  assert.match(text, /charged twice/i);
  assert.match(text, /CUSTOMER/);
  assert.match(text, /ADVISOR/);
  await card.locator('summary', { hasText: 'points were lost' }).click();
  assert.match(await card.locator('.lost').first().innerText(), /transferred|asked the customer to explain|refund/i);
  await ctx.close();
});

test('quality: a mono recording is refused with a clear message', async (t) => {
  const h = await agentsUp();
  if (!h || !h.listen) return t.skip('the Python agents or the speech model are not available');
  const { ctx, page } = await signIn('nour');
  await page.goto(`${BASE}/quality`);
  const n = 16000, data = Buffer.alloc(n * 2);
  for (let i = 0; i < n; i++) data.writeInt16LE(Math.round(8000 * Math.sin(i / 20)), i * 2);
  const head = Buffer.alloc(44);
  head.write('RIFF', 0); head.writeUInt32LE(36 + data.length, 4); head.write('WAVEfmt ', 8); head.writeUInt32LE(16, 16); head.writeUInt16LE(1, 20); head.writeUInt16LE(1, 22);
  head.writeUInt32LE(16000, 24); head.writeUInt32LE(32000, 28); head.writeUInt16LE(2, 32); head.writeUInt16LE(16, 34); head.write('data', 36); head.writeUInt32LE(data.length, 40);
  await page.setInputFiles('#rec-file', { name: 'mono.wav', mimeType: 'audio/wav', buffer: Buffer.concat([head, data]) });
  await page.click('#audio-form button[type=submit]');
  await page.waitForFunction(() => /two-channel/.test(document.getElementById('audio-status').textContent), null, { timeout: 30000 });
  assert.match(await page.textContent('#audio-status'), /advisor on the left/);
  assert.match(page.url(), /\/quality$/, 'the page stays where it is');
  await ctx.close();
});

test('quality: the page says how accurate the analyst is, rule by rule, with its known mistakes', async (t) => {
  const { ctx, page } = await signIn('nour');
  await page.goto(`${BASE}/quality`);
  const acc = page.locator('section[aria-labelledby=acc]');
  if (!(await acc.count())) { await ctx.close(); return t.skip('the demo data has no accuracy report'); }
  assert.match(await acc.locator('.result').innerText(), /hand-labelled calls that were never used to tune it/);
  assert.match(await acc.locator('.result').innerText(), /\d+%\s*of the time \(precision\)/);
  await acc.locator('summary', { hasText: 'Rule by rule' }).click();
  assert.ok(await acc.locator('table tbody tr:visible').count() >= 15, 'every rule has a row');
  await acc.locator('summary', { hasText: 'How it was measured' }).click();
  assert.match(await acc.innerText(), /never looked at/);
  await acc.locator('summary', { hasText: 'Known mistakes' }).click();
  assert.ok(await acc.locator('details').last().locator('li').count() >= 1, 'the mistakes are listed, not hidden');
  await ctx.close();
});

test('quality: a reviewer can dispute a finding (the score follows) and take the verdict back', async (t) => {
  if (!(await agentsUp())) return t.skip('the Python agents are not running');
  // a call where "no closing question" cost a point in a criterion that is not at its floor, so removing it must raise the score
  const all = await (await fetch('http://localhost:8000/quality/reviews?limit=100')).json();
  const pick = all.find((r) => !r.adjusted && r.errors.some((e) => e.rule === 'no_closing')
    && r.errors.filter((e) => e.criterion === 'Resolution').reduce((n, e) => n + e.points, 0) <= 8);
  assert.ok(pick, 'a suitable call exists in the history');
  const id = pick.callId;
  const { ctx, page } = await signIn('nour');
  await page.goto(`${BASE}/quality?call=${id}`);
  const scoreOf = async () => Number((await page.locator(`article#${id} .score`).innerText()).split('/')[0]);
  const before = await scoreOf();
  const card = page.locator(`article#${id}`);
  await card.locator('summary', { hasText: 'points were lost' }).click();
  await card.locator('.lost li', { hasText: 'without a closing question' }).locator('button.fb[data-verdict="disagree"]').click();
  await page.waitForSelector(`article#${id} .lost li.disputed`);                       // the page reloaded with the verdict applied...
  assert.ok(await page.locator(`article#${id} details.lost`).first().evaluate((d) => d.open), '...and the list is open again')
  assert.ok((await scoreOf()) > before, 'the disputed finding no longer costs points');
  assert.match(await page.locator(`article#${id} .meta`).innerText(), /adjusted after review \(was \d+\)/);
  const disputed = page.locator(`article#${id} .lost li.disputed`);
  assert.equal(await disputed.count(), 1);
  assert.match(await disputed.innerText(), /Left out of the score/);
  assert.match(await page.locator('.agreement').innerText(), /checked \d+ findings/);
  await disputed.locator('button.fb[data-verdict="disagree"]').click();          // the pressed button again takes the verdict back
  await page.waitForFunction((i) => !document.querySelector(`#${i} .lost li.disputed`), id);
  assert.equal(await scoreOf(), before);
  await ctx.close();
});

test('quality: filters narrow the reviews by error and by score', async (t) => {
  if (!(await agentsUp())) return t.skip('the Python agents are not running');
  const { ctx, page } = await signIn('nour');
  await page.goto(`${BASE}/quality`);
  await page.selectOption('#byrule', 'no_identity_check');
  await page.selectOption('#below', '70');
  await page.click('.filters-form button[type=submit]');
  await page.waitForURL(/rule=no_identity_check&below=70/);
  const cards = page.locator('article.review');
  assert.ok(await cards.count() >= 1, 'some calls match');
  for (const card of await cards.all()) {
    assert.ok(Number((await card.locator('.score').innerText()).split('/')[0]) < 70);
    assert.match(await card.locator('details.lost').first().textContent(), /before verifying the customer's identity/);
  }
  assert.equal(await page.locator('#byrule').inputValue(), 'no_identity_check');
  await page.click('.filters-form a.btn-quiet');
  await page.waitForURL(/\/quality$/);
  await ctx.close();
});

test('call review: the emotion answer comes with a map of which parts of the recording it leaned on', async (t) => {
  let up = false;
  try { up = (await fetch('http://localhost:8001/health')).ok; } catch { /* not running */ }
  if (!up) return t.skip('the emotion service is not running');
  const { ctx, page } = await signIn('nour');
  await page.goto(`${BASE}/call-review`);
  assert.equal(await page.locator('#r-why-box').isVisible(), false, 'hidden until there is a result');
  const n = 16000 * 3, data = Buffer.alloc(n * 2);
  for (let i = 0; i < n; i++) data.writeInt16LE(Math.round(9000 * Math.sin(i / (i < n / 2 ? 18 : 40)) * (1 + Math.sin(i / 3000)) / 2), i * 2);
  const head = Buffer.alloc(44);
  head.write('RIFF', 0); head.writeUInt32LE(36 + data.length, 4); head.write('WAVEfmt ', 8); head.writeUInt32LE(16, 16); head.writeUInt16LE(1, 20); head.writeUInt16LE(1, 22);
  head.writeUInt32LE(16000, 24); head.writeUInt32LE(32000, 28); head.writeUInt16LE(2, 32); head.writeUInt16LE(16, 34); head.write('data', 36); head.writeUInt32LE(data.length, 40);
  await page.setInputFiles('#audio', { name: 'tone.wav', mimeType: 'audio/wav', buffer: Buffer.concat([head, data]) });
  await page.click('#review-form button[type=submit]');
  await page.locator('#r-why-box').waitFor({ state: 'visible', timeout: 90000 });
  assert.ok(await page.locator('#r-why li').count() >= 5, 'one block per half second');
  assert.match(await page.locator('#r-why-top').innerText(), /Most influential: [\d.]+ to [\d.]+ s|No single part/);
  assert.match(await page.locator('#r-why li').first().getAttribute('aria-label'), /s: (supports|argues against|no effect on) /);
  await ctx.close();
});

test('sales: offers come with their reasons in points, a conversation is read, and an outcome is recorded', async (t) => {
  if (!(await agentsUp())) return t.skip('the Python agents are not running');
  const { ctx, page } = await signIn('leila');
  await page.goto(`${BASE}/sales`);
  assert.ok(await page.locator('#opps .opp').count() >= 3, 'an offer for each customer on file');
  const first = page.locator('#opps .opp').first();
  await first.locator('summary', { hasText: 'Why this offer' }).click();
  const whyOffer = first.locator('details:has(summary:text("Why this offer")) .driver-list');
  assert.match(await whyOffer.innerText(), /What the file says[\s\S]*Fit with the contract/);
  assert.ok(await whyOffer.locator('.eff').count() >= 3, 'every factor has its points');
  // a conversation: the customer says she is travelling, the agent finds the need and the roaming offer
  await page.click('button[data-sample-customer="YT-1042"]');
  assert.match(await page.inputValue('#sales-text'), /travelling to Paris/);
  await page.click('#sales-form button[type=submit]');
  await page.locator('#sales-result').waitFor({ state: 'visible', timeout: 20000 });
  assert.match(await page.locator('#sales-signals').innerText(), /Travelling abroad[\s\S]*Paris/);
  const offers = page.locator('#sales-offers > li');
  assert.match(await offers.first().innerText(), /Roaming Pass 5 GB: \d+\/100/);
  assert.match(await offers.first().locator('.driver-list').innerText(), /What the customer said/);
  await offers.first().locator('button[data-outcome=accepted]').click();
  await page.locator('.toast', { hasText: 'Recorded: accepted' }).waitFor({ timeout: 10000 });
  assert.equal(await offers.first().locator('button[data-outcome]').first().isDisabled(), true, 'one outcome per offer');
  assert.ok(await page.locator('table.conv').count() >= 4, 'what converts');
  // propensity: churn risk, the chance of a yes and what it is worth, on the card and in the conversation reader
  assert.match(await first.locator('.risk').innerText(), /Churn risk \d+ · (Low|Medium|High)/);
  assert.match(await first.locator('.figures').innerText(), /Chance of a yes \d+% · worth -?\d+ TND over 12 months if yes · expected -?\d+ TND/);
  await first.locator('summary', { hasText: 'Why this churn risk' }).click();
  assert.match(await first.locator('details:has(summary:text("Why this churn risk")) .driver-list').innerText(), /Starting point/);
  assert.match(await offers.first().locator('.figures').innerText(), /Chance of a yes \d+%/);
  assert.match(await page.locator('#sales-churn').innerText(), /Risk of losing this customer: \d+ · /);
  // commercial simulation: a stricter rule makes fewer offers, then redraws the table
  const rows = page.locator('#sim-body tr');
  assert.equal(await rows.count(), 5, 'four rules and yours');
  const offersBefore = Number((await rows.last().locator('td').first().innerText()).trim());
  await page.fill('#sim-min', '70');
  await page.check('#sim-good');
  await page.click('#sim-form button[type=submit]');
  await page.waitForFunction(() => /relevance 70 or more, at a good moment/i.test(document.querySelector('#sim-body tr.yours th')?.textContent ?? ''), null, { timeout: 15000 });
  const offersAfter = Number((await rows.last().locator('td').first().innerText()).trim());
  assert.ok(offersAfter < offersBefore, 'fewer offers under a stricter rule');
  await page.fill('#sim-calls', '2000');
  await page.click('#sim-form button[type=submit]');
  await page.waitForFunction(() => /2000 calls/.test(document.querySelector('#sim-caption')?.textContent ?? ''), null, { timeout: 15000 });
  await ctx.close();
});

test('sales in the live call: an offer to keep in mind appears with its timing and the advisor reports the outcome', async (t) => {
  if (!(await agentsUp())) return t.skip('the Python agents are not running');
  const { ctx, page } = await signIn('karim');
  await page.goto(`${BASE}/advisor`);
  await page.uncheck('#lv-voice'); await page.uncheck('#lv-sayme');
  assert.equal(await page.locator('#live-offer').isVisible(), false, 'no offer before a call');
  await page.click('#live-setup button[type=submit]');
  await page.locator('#live-offer').waitFor({ state: 'visible', timeout: 20000 });
  assert.match(await page.locator('#lv-o-name').innerText(), /Upgrade to Premium Unlimited \(\d+\/100\)/);
  assert.match(await page.locator('#lv-o-timing').innerText(), /Wait: solve the problem first/);   // the customer file has an open ticket
  assert.match(await page.locator('#lv-o-risk').innerText(), /Risk of losing this customer: \d+ · (Low|Medium|High)/);
  assert.match(await page.locator('#lv-o-figures').innerText(), /Chance of a yes \d+% · worth \d+ TND over 12 months if yes · expected \d+ TND/);
  await page.locator('#live-offer summary', { hasText: 'Why this offer' }).click();
  assert.match(await page.locator('#lv-o-why').innerText(), /What the file says[\s\S]*The moment/);
  // the advisor answers; the panel follows the conversation and the outcome can be reported once
  await page.fill('#lv-text', 'I am sorry about this. Let me check the refund policy before I promise anything.');
  await page.click('#live-say button[type=submit]');
  await page.locator('.live-msg.client').nth(1).waitFor({ timeout: 20000 });
  await page.locator('#lv-o-name').waitFor({ state: 'visible' });
  await page.click('#lv-o-actions button[data-outcome=declined]');
  await page.locator('.toast', { hasText: 'Recorded: declined' }).waitFor({ timeout: 10000 });
  assert.equal(await page.locator('#lv-o-actions button[data-outcome]').first().isDisabled(), true, 'one outcome per offer');
  await ctx.close();
});

test('complaints: cases come with their reasons, a complaint is read, opened, taken, resolved and closed after the follow-up', async (t) => {
  if (!(await agentsUp())) return t.skip('the Python agents are not running');
  const { ctx, page } = await signIn('admin');
  await page.goto(`${BASE}/complaints`);
  assert.ok(await page.locator('.lane').count() >= 4, 'critical, high, medium and low lanes');
  assert.ok(await page.locator('.case').count() >= 4 && await page.locator('.early-warning').count() >= 1, 'open cases and an early warning');
  const card = page.locator('.case').first();
  await card.locator('summary', { hasText: 'Why' }).click();
  assert.ok(await card.locator('.driver-list .eff').count() >= 3, 'every number has its points');
  // read a complaint without saving it
  await page.click('button[data-tri-sample]:has-text("Charged twice")');
  await page.click('#tri-read');
  await page.locator('#tri-result').waitFor({ state: 'visible', timeout: 20000 });
  assert.match(await page.locator('#tri-cluster').innerText(), /Billing duplicates/);
  assert.match(await page.locator('#tri-level').innerText(), /(Critical|High) · escalation risk \d+/);
  assert.ok(await page.locator('#tri-sev li').count() >= 2 && await page.locator('#tri-actions li').count() >= 3);
  // open it as a case, then take it, resolve it and close it after the follow-up call
  await page.click('#tri-form button[type=submit]');
  await page.waitForURL(/\/complaints\/CMP-\d+$/);
  assert.match(await page.textContent('main'), /Why this level and this risk[\s\S]*What to do first/);
  await page.click('button:has-text("Take case")');
  assert.match(await page.textContent('.page-head .lede'), /taken by admin/);
  await page.selectOption('#res', 'refunded');
  await page.fill('#res-note', 'refunded the duplicate');
  await page.click('button:has-text("Resolve")');
  assert.match(await page.textContent('main'), /Follow-up call: is the customer satisfied\?/);
  await page.selectOption('#tr', 'yes');
  await page.click('button:has-text("Close the follow-up")');
  assert.match(await page.textContent('main'), /Closed: the customer is satisfied/);
  assert.match(await page.textContent('main'), /opened[\s\S]*taken[\s\S]*resolved[\s\S]*closed/);
  // a call the quality analyst scored badly can become a case
  await page.goto(`${BASE}/complaints`);
  const open = page.locator('form[action="/complaints/from-call"] button');
  if (await open.count()) {
    await open.first().click();
    await page.waitForURL(/\/complaints\/CMP-\d+$/);
    assert.match(await page.textContent('main'), /from the call/);
  }
  await ctx.close();
});
