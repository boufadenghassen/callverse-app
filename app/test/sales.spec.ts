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
  acceptance: { probability: 0.43, similar: 6, similarAccepted: 3, basis: '6 similar offers in the history (relevance under 50, problem not solved yet): 3 accepted; this offer overall: 41% of 24' },
  expected: { ifYes: 96, chance: 0.43, tnd: 41, how: '8 TND more x 12 months' },
  churn: { score: 17, level: 'Low', factors: [{ name: 'Starting point', points: 10, why: 'every customer has some risk' }, { name: 'Open tickets', points: 8, why: '1 open' }, { name: 'Years with us', points: -10, why: '6 years' }] },
};
const SIM: m.SalesSimulation = {
  calls: 1000, share: 30, opportunities: 300, simulated: 240, history: 240, method: 'Replays the history.',
  policies: [{ label: 'Offer at every opportunity', minRelevance: 0, goodMomentOnly: false, offers: 300, accepted: 85, declined: 215, rate: 0.28, revenue: 7235, perCall: 7.24 }],
  yours: { label: 'Yours: relevance 0 or more', minRelevance: 0, goodMomentOnly: false, offers: 300, accepted: 85, declined: 215, rate: 0.28, revenue: 7235, perCall: 7.24 },
};
const seen: { outcomes: m.SalesOutcome[]; detects: { id: string | null; turns: m.SalesTurn[] }[]; sims: m.SalesSimulationRequest[] } = { outcomes: [], detects: [], sims: [] };

class FakeSalesGateway extends MockAgentGateway {
  async opportunities() { return [OFFER]; }
  async salesDetect(id: string | null, turns: m.SalesTurn[]): Promise<m.SalesDetection> {
    seen.detects.push({ id, turns });
    if (id === 'ZZ-0000') throw new RejectedError('no such customer');
    return { customerId: id, customer: 'Yasmine Toumi', mood: 55, churn: OFFER.churn, signals: [], offers: [OFFER, { ...OFFER, offerId: 'data-booster' }, { ...OFFER, offerId: 'autopay' }], skipped: [] };
  }
  async salesOutcome(o: m.SalesOutcome) { seen.outcomes.push(o); }
  async salesSimulate(r: m.SalesSimulationRequest) { seen.sims.push(r); return SIM; }
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

test('the page shows the churn risk, the chance of a yes, what a yes is worth, and the simulation', async () => {
  const html = (await (await client(real, 'leila')).get('/sales').expect(200)).text;
  assert.match(html, /class="risk low">Churn risk 17 · Low/);
  assert.match(html, /Why this churn risk/);
  assert.match(html, /Chance of a yes <strong>43%<\/strong> · worth <strong>96 TND<\/strong> over 12 months if yes · expected <strong>41 TND<\/strong>/);
  assert.match(html, /6 similar offers in the history/);
  assert.match(html, /What a selling rule would earn/);
  assert.match(html, /One month: 1000 calls, 300 with a chance to offer/);
  assert.match(html, /<td>7235<\/td>/);
  const demoHtml = (await (await client(demo, 'leila')).get('/sales').expect(200)).text;
  assert.doesNotMatch(demoHtml, /What a selling rule would earn|Churn risk/);                      // the demo data has neither
});

test('a selling rule is validated before it is replayed, and demo mode cannot do it', async () => {
  const leila = await client(real, 'leila');
  const token = tokenOf((await leila.get('/sales')).text);
  const send = (b: object) => leila.post('/sales/simulate').set('X-CSRF-Token', token).send(b);
  const good = { calls: 500, share: 20, minRelevance: 60, goodMomentOnly: true };
  for (const bad of [{ ...good, calls: 0 }, { ...good, calls: 100001 }, { ...good, calls: 2.5 }, { ...good, share: 101 }, { ...good, minRelevance: -1 }, { ...good, goodMomentOnly: 'yes' }, { ...good, calls: '500' }]) {
    await send(bad).expect(400);
  }
  assert.equal((await send(good).expect(200)).body.opportunities, 300);
  assert.deepEqual(seen.sims.at(-1), good);
  await leila.post('/sales/simulate').send(good).expect(403);                                      // no CSRF token
  await (await client(real, 'karim')).post('/sales/simulate').send(good).expect(403);              // wrong role
  const demoLeila = await client(demo, 'leila');
  const demoToken = tokenOf((await demoLeila.get('/sales')).text);
  assert.match((await demoLeila.post('/sales/simulate').set('X-CSRF-Token', demoToken).send(good).expect(503)).body.error, /real agents/);
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
      if (req.url === '/sales/simulate') { if (body.includes('"calls":0')) { res.statusCode = 422; return res.end('{}'); } return res.end(JSON.stringify(SIM)); }
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
    assert.equal((await gw.salesSimulate({ calls: 1000, share: 30, minRelevance: 70, goodMomentOnly: true })).opportunities, 300);
    assert.match(calls.at(-1)!, /POST \/sales\/simulate \{"calls":1000,"share":30,"min_relevance":70,"good_moment_only":true\}/);
    await assert.rejects(() => gw.salesSimulate({ calls: 0, share: 30, minRelevance: 0, goodMomentOnly: false }), RejectedError);
    process.env.CALLVERSE_AGENTS_URL = 'http://localhost:1';
    await assert.rejects(() => new HttpAgentGateway().salesAnalytics(), AgentDownError);
  } finally {
    if (was === undefined) delete process.env.CALLVERSE_AGENTS_URL; else process.env.CALLVERSE_AGENTS_URL = was;
    fake.close();
  }
});

test('during a live call the advisor gets at most two offers, read from the conversation so far, with the customer mood', async () => {
  const karim = await client(real, 'karim');
  const token = tokenOf((await karim.get('/advisor')).text);
  const send = (b: object) => karim.post('/advisor/live/offers').set('X-CSRF-Token', token).send(b);
  await send({ turns: [] }).expect(400);
  await send({ turns: [{ speaker: 'robot', text: 'hi' }] }).expect(400);
  await karim.post('/advisor/live/offers').send({ turns: [{ speaker: 'customer', text: 'hi' }] }).expect(403);                       // no CSRF token
  await (await client(real, 'leila')).post('/advisor/live/offers').send({}).expect(403);                                             // not the advisor's console
  const ok = await send({ turns: [
    { speaker: 'customer', text: 'I was charged twice .', mood: 30 }, { speaker: 'advisor', text: 'I am sorry.', mood: 90 },
    { speaker: 'customer', text: 'Thanks.', mood: 140 }, { speaker: 'customer', text: 'Still here.', mood: 41.5 }] }).expect(200);
  assert.equal(ok.body.offers.length, 2);
  assert.equal(ok.body.churn.level, 'Low');
  assert.deepEqual(seen.detects.at(-1), { id: 'YT-1042', turns: [
    { speaker: 'customer', text: 'I was charged twice .', mood: 30 }, { speaker: 'advisor', text: 'I am sorry.' },       // a mood only comes with a customer's words
    { speaker: 'customer', text: 'Thanks.' }, { speaker: 'customer', text: 'Still here.' }] });                                     // and only a whole 0 to 100
  const demoKarim = await client(demo, 'karim');
  const demoToken = tokenOf((await demoKarim.get('/advisor')).text);
  assert.match((await demoKarim.post('/advisor/live/offers').set('X-CSRF-Token', demoToken).send({ turns: [{ speaker: 'customer', text: 'hi' }] }).expect(503)).body.error, /real agents/);
});

test('the advisor can report what the customer did with an offer, a client cannot', async () => {
  const karim = await client(real, 'karim');
  const token = tokenOf((await karim.get('/advisor')).text);
  const good = { customerId: 'YT-1042', offerId: 'plan-upgrade', outcome: 'accepted', relevance: 40, cue: 'after_resolution', need: 'plan_change' };
  await karim.post('/sales/outcome').set('X-CSRF-Token', token).send(good).expect(200);
  assert.equal(seen.outcomes.at(-1)?.outcome, 'accepted');
  const yasmine = await client(real, 'yasmine');
  const yToken = /name="csrf-token" content="([^"]+)"/.exec((await yasmine.get('/client')).text)![1];
  await yasmine.post('/sales/outcome').set('X-CSRF-Token', yToken).send(good).expect(403);
});
