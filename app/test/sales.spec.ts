import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { Test } from '@nestjs/testing';
import { NestExpressApplication } from '@nestjs/platform-express';
import { AgentDownError, AgentGateway, RejectedError } from '../src/agents/agent.gateway';
import { HttpAgentGateway } from '../src/agents/http.gateway';
import { MockAgentGateway } from '../src/agents/mock.gateway';
import * as m from '../src/agents/models';
import { AppModule } from '../src/app.module';
import { setup } from '../src/setup';
import { client, startApp } from './helpers';

/** What the real sales agent answers, shaped like its Python output, so the page and the routes can be tested without Python. */
const OFFER: m.Opportunity = {
  customer: 'Yasmine Toumi', customerId: 'YT-1042', offer: 'Upgrade to Premium Unlimited', offerId: 'plan-upgrade', price: 'from 8 TND more per month', kind: 'up-sell', pitch: 'p',
  relevance: 40, reason: 'Contacted us about: plan change', need: { key: 'plan_change', label: 'Wants a different plan' },
  factors: [{ name: 'What the file says', points: 25, why: 'Contacted us about: plan change' }, { name: 'Fit with the contract', points: 15, why: 'Mobile Plus 40 GB: not already covered' }, { name: 'The moment', points: -10, why: '1 open ticket: solve it first' }],
  timing: { cue: 'after_resolution', why: '1 open ticket: solve it first' }, counterfactual: 'Without “The moment” (1 open ticket: solve it first), the relevance would be 50.', alternatives: [{ offer: 'Data Booster +20 GB', relevance: 31 }],
};
const seen: { outcomes: m.SalesOutcome[]; detects: { id: string | null; turns: m.SalesTurn[] }[] } = { outcomes: [], detects: [] };

class FakeSalesGateway extends MockAgentGateway {
  async opportunities() { return [OFFER]; }
  async salesDetect(id: string | null, turns: m.SalesTurn[]): Promise<m.SalesDetection> {
    seen.detects.push({ id, turns });
    if (id === 'ZZ-0000') throw new RejectedError('no such customer');
    return { customerId: id, customer: 'Yasmine Toumi', mood: 55, signals: [], offers: [OFFER], skipped: [] };
  }
  async salesOutcome(o: m.SalesOutcome) { seen.outcomes.push(o); }
  async salesAnalytics(): Promise<m.SalesAnalytics> {
    const row = { label: 'Data Booster +20 GB', key: 'data-booster', offered: 20, accepted: 9, rate: 0.45 };
    return { total: 240, accepted: 80, rate: 0.33, simulated: 240, byOffer: [row], byRelevance: [row], byMoment: [row], byNeed: [row], method: 'The history is simulated.' };
  }
}

let demo: NestExpressApplication, real: NestExpressApplication;
before(async () => {
  demo = await startApp();
  const moduleRef = await Test.createTestingModule({ imports: [AppModule] }).overrideProvider(AgentGateway).useValue(new FakeSalesGateway()).compile();
  real = moduleRef.createNestApplication<NestExpressApplication>();
  setup(real);
  await real.init();
});
after(async () => { await demo.close(); await real.close(); });

const tokenOf = (html: string) => /data-csrf="([^"]+)"/.exec(html)![1];

test('only sales (and admin) open the sales page; demo mode keeps its two demo cards and offers no conversation reader', async () => {
  await (await client(demo, 'karim')).get('/sales').expect(403);
  const html = (await (await client(demo, 'leila')).get('/sales').expect(200)).text;
  assert.match(html, /Family bundle/);
  assert.doesNotMatch(html, /Read a conversation/);
  assert.doesNotMatch(html, /Why this offer/);
});

test('demo mode refuses to read a conversation or keep an outcome (503), with the right guards', async () => {
  const leila = await client(demo, 'leila');
  const token = tokenOf((await leila.get('/sales')).text);
  const body = { customerId: null, turns: [{ speaker: 'customer', text: 'I am travelling abroad.' }] };
  await leila.post('/sales/detect').send(body).expect(403);                                         // no CSRF token
  await (await client(demo, 'karim')).post('/sales/detect').send(body).expect(403);                  // wrong role
  assert.match((await leila.post('/sales/detect').set('X-CSRF-Token', token).send(body).expect(503)).body.error, /real agents/);
  const out = { customerId: 'YT-1042', offerId: 'data-booster', outcome: 'accepted', relevance: 70, cue: 'now', need: 'data_short' };
  assert.match((await leila.post('/sales/outcome').set('X-CSRF-Token', token).send(out).expect(503)).body.error, /real agents/);
});

test('with the real agent the page shows each offer with its reasons in points, the reader and what converts', async () => {
  const html = (await (await client(real, 'leila')).get('/sales').expect(200)).text;
  assert.match(html, /Upgrade to Premium Unlimited/);
  assert.match(html, /Why this offer/);
  assert.match(html, /<span class="eff pos">\+25<\/span>/);
  assert.match(html, /<span class="eff neg">−10<\/span>/);
  assert.match(html, /Wait: solve the problem first/);
  assert.match(html, /the relevance would be 50/);
  assert.match(html, /Read a conversation/);
  assert.match(html, /data-sample-customer="YT-1042"/);
  assert.match(html, /Which offers convert/);
  assert.match(html, /80 of 240 offers accepted \(33%\)/);
  assert.match(html, /240 simulated/);
});

test('a conversation is cleaned, validated and passed on; an unknown customer is refused', async () => {
  const leila = await client(real, 'leila');
  const token = tokenOf((await leila.get('/sales')).text);
  const send = (b: object) => leila.post('/sales/detect').set('X-CSRF-Token', token).send(b);
  await send({ turns: [] }).expect(400);
  await send({ customerId: 'not-an-id', turns: [{ speaker: 'customer', text: 'hi' }] }).expect(400);
  await send({ customerId: 'YT-1042', turns: [{ speaker: 'robot', text: 'hi' }, { speaker: 'customer', text: '   ' }] }).expect(400);
  await send({ customerId: 'ZZ-0000', turns: [{ speaker: 'customer', text: 'hello' }] }).expect(400);
  const ok = await send({ customerId: 'YT-1042', turns: [{ speaker: 'customer', text: 'Going abroad\u0000 next week.' }, { speaker: 'advisor', text: 'Sure.' }] }).expect(200);
  assert.equal(ok.body.offers[0].offerId, 'plan-upgrade');
  assert.deepEqual(seen.detects.at(-1), { id: 'YT-1042', turns: [{ speaker: 'customer', text: 'Going abroad  next week.' }, { speaker: 'advisor', text: 'Sure.' }] });
});

test('an outcome is validated before it is kept', async () => {
  const leila = await client(real, 'leila');
  const token = tokenOf((await leila.get('/sales')).text);
  const good = { customerId: 'YT-1042', offerId: 'plan-upgrade', outcome: 'declined', relevance: 40, cue: 'after_resolution', need: 'plan_change' };
  const send = (b: object) => leila.post('/sales/outcome').set('X-CSRF-Token', token).send(b);
  for (const bad of [{ ...good, offerId: '../etc' }, { ...good, outcome: 'maybe' }, { ...good, relevance: 101 }, { ...good, relevance: 4.5 }, { ...good, cue: 'later' }, { ...good, need: 'Not Valid' }, { ...good, customerId: 'x' }]) {
    await send(bad).expect(400);
  }
  assert.deepEqual((await send(good).expect(200)).body, { recorded: true });
  assert.deepEqual(seen.outcomes.at(-1), { customerId: 'YT-1042', offerId: 'plan-upgrade', outcome: 'declined', relevance: 40, cue: 'after_resolution', need: 'plan_change' });
});

test('the http gateway reads the Python sales agent and maps its refusals', async () => {
  const calls: string[] = [];
  const fake = createServer((req, res) => {
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => {
      calls.push(`${req.method} ${req.url} ${body}`);
      res.setHeader('Content-Type', 'application/json');
      if (req.url === '/sales/detect' && body.includes('ZZ-0000')) { res.statusCode = 404; return res.end('{}'); }
      if (req.url === '/sales/outcome' && body.includes('nothing')) { res.statusCode = 404; return res.end('{}'); }
      res.end(req.url === '/sales/opportunities' ? JSON.stringify([OFFER]) : req.url === '/sales/analytics' ? '{"total":1}' : '{"customerId":null,"customer":null,"mood":55,"signals":[],"offers":[],"skipped":[]}');
    });
  });
  await new Promise<void>((ok) => fake.listen(0, ok));
  const was = process.env.CALLVERSE_AGENTS_URL;
  process.env.CALLVERSE_AGENTS_URL = `http://localhost:${(fake.address() as { port: number }).port}`;
  try {
    const gw = new HttpAgentGateway();
    assert.equal((await gw.opportunities())[0].factors?.length, 3);
    assert.equal((await gw.salesAnalytics())?.total, 1);
    await gw.salesDetect('YT-1042', [{ speaker: 'customer', text: 'hi' }]);
    assert.match(calls.at(-1)!, /POST \/sales\/detect \{"customer_id":"YT-1042","turns":\[\{"speaker":"customer","text":"hi"\}\]\}/);
    await assert.rejects(() => gw.salesDetect('ZZ-0000', [{ speaker: 'customer', text: 'hi' }]), RejectedError);
    await gw.salesOutcome({ customerId: 'YT-1042', offerId: 'data-booster', outcome: 'accepted', relevance: 70, cue: 'now', need: 'data_short' });
    assert.match(calls.at(-1)!, /POST \/sales\/outcome \{"customer_id":"YT-1042","offer_id":"data-booster","outcome":"accepted","relevance":70,"cue":"now","need":"data_short"\}/);
    await assert.rejects(() => gw.salesOutcome({ customerId: null, offerId: 'nothing', outcome: 'accepted', relevance: 0, cue: 'now', need: '' }), RejectedError);
    process.env.CALLVERSE_AGENTS_URL = 'http://localhost:1';
    await assert.rejects(() => new HttpAgentGateway().salesAnalytics(), AgentDownError);
  } finally {
    if (was === undefined) delete process.env.CALLVERSE_AGENTS_URL; else process.env.CALLVERSE_AGENTS_URL = was;
    fake.close();
  }
});
