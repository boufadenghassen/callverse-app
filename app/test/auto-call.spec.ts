import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { Test } from '@nestjs/testing';
import { NestExpressApplication } from '@nestjs/platform-express';
import { AgentGateway } from '../src/agents/agent.gateway';
import { MockAgentGateway } from '../src/agents/mock.gateway';
import * as m from '../src/agents/models';
import { AppModule } from '../src/app.module';
import { simSettings } from '../src/pages/scenario-sim';
import { setup } from '../src/setup';
import { client, startApp } from './helpers';

const REAL: m.ScenarioDetail = {
  id: 'sc_abc', title: 'Refund follow-up (level 4, en)', profile: 'Loyal', difficulty: 'Hard', origin: 'Template library', kind: 'generated',
  spec: { segment: 'at_risk', difficulty: 4, intent: 'cancellation_request', events: ['repeat_caller', 'threatens_to_leave'], language: 'en' }, opening_emotion: 'fear',
  trainer_brief: 'Practise: cancellation request with an at-risk customer.', success_criteria: ['Keeps the customer', 'Confirms in writing'],
};

test('a scenario of the generator becomes the simulator settings, with the reasons', () => {
  const s = simSettings(REAL);
  assert.deepEqual({ persona: s.persona, mix: s.mix, difficulty: s.difficulty, intent: s.intent, memory: s.memory }, { persona: 'LOYAL_AT_RISK', mix: 'ANXIOUS', difficulty: 'HARD', intent: 'CANCELLATION', memory: true });
  assert.equal(s.why.length, 5);
  assert.match(s.why.join(' '), /at risk customer.*Loyal but at risk/);
  assert.match(s.why.join(' '), /afraid: mixed with “Anxious first-timer”/);
  assert.match(s.why.join(' '), /cancellation request becomes “Cancellation”, the closest of the simulator's three reasons/);
  assert.match(s.why.join(' '), /Difficulty 4\/5 becomes “Hard”/);
  assert.match(s.why.join(' '), /repeat caller/);
  const easy = simSettings({ ...REAL, spec: { segment: 'new', difficulty: 2, intent: 'double_billing', events: [] }, opening_emotion: 'neutral' });
  assert.deepEqual({ persona: easy.persona, mix: easy.mix, difficulty: easy.difficulty, intent: easy.intent, memory: easy.memory }, { persona: 'NEW_SUBSCRIBER', mix: null, difficulty: 'EASY', intent: 'BILLING', memory: false });
  assert.equal(simSettings({ ...REAL, spec: { segment: 'premium', difficulty: 3, intent: 'slow_internet' } }).intent, 'ROAMING');
  assert.equal(simSettings({ ...REAL, spec: { segment: 'premium', difficulty: 3, intent: 'something_new' } }).intent, 'BILLING', 'an intent the table does not know falls back to billing');
  assert.equal(simSettings({ ...REAL, spec: { segment: 'dissatisfied', difficulty: 5 }, opening_emotion: undefined }).persona, 'IMPATIENT');
});

test('a demo scenario (a card only) is read from its profile, difficulty and title', () => {
  const s = simSettings({ id: 'SC-31', title: 'Double charge, customer threatens to post online', profile: 'Unsatisfied', difficulty: 'Hard', origin: 'QA weakness: compliance' });
  assert.deepEqual({ persona: s.persona, difficulty: s.difficulty, intent: s.intent, memory: s.memory }, { persona: 'IMPATIENT', difficulty: 'HARD', intent: 'BILLING', memory: false });
  assert.equal(simSettings({ id: 'x', title: 'Roaming bundle unusable abroad', profile: 'Premium', difficulty: 'Medium', origin: '' }).intent, 'ROAMING');
});

let demo: NestExpressApplication, real: NestExpressApplication;
const asked: { topic: string; turn: number; style: string }[] = [];
const contexts: (m.AutoContext | undefined)[] = [], calls: m.CallConfig[] = [], reviewed: string[][] = [];
const ATTEMPT: m.PracticeAttempt = { callId: 'CALL-3501', scenarioId: 'sc_abc', title: 'Refund follow-up (level 4, en)', advisor: 'Hela M.', overall: 88, date: '2026-11-05', next: 'harder', advice: 'Passed at 88/100 with nothing worse than usual: try the harder version.',
  changes: [{ criterion: 'Compliance', before: 5.1, after: 9, status: 'improved' }] };
class FakeGateway extends MockAgentGateway {
  async scenario(id: string) { if (id === 'nope') throw new Error('Unknown scenario'); return id === 'SC-31' ? super.scenario(id) : { ...REAL, id, opening_line: 'I lost my phone.', call_topic: 'my lost SIM', customer_card: 'You lost your phone.', complications: ['The customer is abroad.'] }; }
  async startCall(c: m.CallConfig): Promise<m.CallStart> { calls.push(c); return { id: '0123456789abcdef', persona: 'Impatient', opening: c.opening ?? 'Hello', mood: 50, patience: 60 }; }
  async practiceCall(callId: string, scenarioId: string, advisor: string) { reviewed.push(['practice', scenarioId, advisor]); return { ...(await this.reviewCall(callId, advisor)), practice: ATTEMPT }; }
  async practice(advisor: string): Promise<m.PracticeHistory> { return advisor === 'Hela M.' ? { attempts: [ATTEMPT], count: 1, best: 88, trend: null } : { attempts: [], count: 0, best: null, trend: null }; }
  async autoReply(topic: string, turn: number, style: 'careful' | 'rushed', context?: m.AutoContext): Promise<m.AutoReply> {
    asked.push({ topic, turn, style });
    contexts.push(context);
    return { text: 'I am sorry about this.', step: 'acknowledge', turn, last: false, sources: ['Billing policy §4.2'], intents: ['Billing'], policyWarning: null, style };
  }
  async reviewCall(callId: string, advisor: string, source?: 'live call' | 'automatic'): Promise<m.QualityReview> {
    reviewed.push(['review', advisor, source ?? '']);
    return {
      callId: 'CALL-3500', advisor, overall: 92, counterfactual: '', criteria: [],
      errors: [{ rule: 'no_closing', criterion: 'Resolution', points: 2, turn: 4, timestamp: '00:30', quote: '', reason: 'The call ended without a closing question', fix: '', cause: 'Soft skills' }],
      drivers: {
        hurt: [{ turn: 4, timestamp: '00:30', rule: 'no_closing', label: 'The call ended without a closing question', effect: -2, quote: '' }],
        helped: [{ turn: 1, timestamp: '00:05', rule: 'empathy', label: 'Acknowledged the customer\'s feelings', effect: 5, quote: '' }, { turn: 0, timestamp: '00:00', rule: 'greeting', label: 'Greeted the customer', effect: 0, quote: '' }],
      },
    };
  }
}
before(async () => {
  demo = await startApp();
  const moduleRef = await Test.createTestingModule({ imports: [AppModule] }).overrideProvider(AgentGateway).useValue(new FakeGateway()).compile();
  real = moduleRef.createNestApplication<NestExpressApplication>();
  setup(real);
  await real.init();
});
after(async () => { await demo.close(); await real.close(); });
const tokenOf = (html: string) => /name="csrf-token" content="([^"]+)"/.exec(html)![1];

test('the advisor console loads a training scenario: the settings are chosen, the reasons and the brief are shown, the call can start by itself', async () => {
  const karim = await client(real, 'karim');
  const html = (await karim.get('/advisor').query({ scenario: 'sc_abc', start: '1' }).expect(200)).text;
  assert.match(html, /Training scenario: Refund follow-up/);
  assert.match(html, /<option value="LOYAL_AT_RISK" selected>/);
  assert.match(html, /<option value="CANCELLATION" selected>/);
  assert.match(html, /<option value="HARD" selected>/);
  assert.doesNotMatch(html, /<option value="MEDIUM" selected>/);
  assert.match(html, /id="lv-memory" type="checkbox" checked/);
  assert.match(html, /id="lv-mix" value="ANXIOUS"/);
  assert.match(html, /Trainer brief:<\/strong> Practise: cancellation request/);
  assert.match(html, /Keeps the customer/);
  assert.match(html, /data-autostart="start"/);
  assert.match((await karim.get('/advisor').query({ scenario: 'sc_abc', auto: 'rushed' })).text, /data-autostart="rushed"/);
  assert.match((await karim.get('/advisor').query({ scenario: 'sc_abc', auto: 'weird' })).text, /data-autostart=""/);
  const plain = (await karim.get('/advisor').expect(200)).text;
  assert.match(plain, /data-autostart=""/);
  assert.match(plain, /<option value="MEDIUM" selected>/);
  assert.match(plain, /Or practise a training scenario: <a href="\/advisor\?scenario=SC-31/);
  assert.match((await karim.get('/advisor').query({ scenario: 'nope' }).expect(200)).text, /That training scenario was not found\./);
  await karim.get('/advisor').query({ scenario: '../etc' }).expect(400);
  assert.match(plain, /data-auto="careful"[\s\S]*data-auto="rushed"/);
});

test('the demo scenarios (cards) can be played too, and the trainer may use the console', async () => {
  const rim = await client(demo, 'rim');
  const html = (await rim.get('/advisor').query({ scenario: 'SC-31' }).expect(200)).text;
  assert.match(html, /Training scenario: Double charge/);
  assert.match(html, /<option value="HARD" selected>/);
  await (await client(demo, 'yasmine')).get('/advisor').expect(403);
  const scenarioPage = (await (await client(real, 'rim')).get('/training/scenarios/SC-31').expect(200)).text;
  assert.match(scenarioPage, /Practise this scenario/);
  assert.match(scenarioPage, /href="\/advisor\?scenario=SC-31&amp;start=1#live"/);
  assert.match(scenarioPage, /href="\/advisor\?scenario=SC-31&amp;auto=careful#live"/);
});

test('the advisor agent answers by itself: validated, guarded, and demo mode says it needs the real agents', async () => {
  const karim = await client(real, 'karim');
  const token = tokenOf((await karim.get('/advisor')).text);
  const send = (b: object) => karim.post('/advisor/live/auto').set('X-CSRF-Token', token).send(b);
  for (const bad of [{ topic: 'hi', turn: 0 }, { topic: 'I was charged twice', turn: 11 }, { topic: 'I was charged twice', turn: -1 }, { topic: 'I was charged twice', turn: 1.5 }, { topic: 'I was charged twice', turn: 0, style: 'angry' }, { turn: 0 }]) {
    await send(bad).expect(400);
  }
  const ok = await send({ topic: 'I was charged twice\u0000 on my bill.', turn: 2, style: 'rushed' }).expect(200);
  assert.equal(ok.body.step, 'acknowledge');
  assert.deepEqual(asked.at(-1), { topic: 'I was charged twice  on my bill.', turn: 2, style: 'rushed' });
  await send({ topic: 'I was charged twice', turn: 0 }).expect(200);
  assert.equal(asked.at(-1)!.style, 'careful', 'the careful routine is the default');
  await karim.post('/advisor/live/auto').send({ topic: 'I was charged twice', turn: 0 }).expect(403);                      // no CSRF token
  const yasmine = await client(real, 'yasmine');
  const yToken = tokenOf((await yasmine.get('/client')).text);                                                              // fetched before the request is made
  await yasmine.post('/advisor/live/auto').set('X-CSRF-Token', yToken).send({ topic: 'I was charged twice', turn: 0 }).expect(403);
  const demoKarim = await client(demo, 'karim');
  const demoToken = tokenOf((await demoKarim.get('/advisor')).text);
  assert.match((await demoKarim.post('/advisor/live/auto').set('X-CSRF-Token', demoToken).send({ topic: 'I was charged twice', turn: 0 }).expect(503)).body.error, /real agents/);
});

test('scoring the call says what lowered it, what went well and whether it ended badly, for the advisor and for the trainer', async () => {
  const id = '0123456789abcdef';
  for (const user of ['karim', 'rim']) {
    const agent = await client(real, user);
    const token = tokenOf((await agent.get('/advisor')).text);
    const r = await agent.post('/advisor/live/review').set('X-CSRF-Token', token).send({ id }).expect(200);
    assert.deepEqual(r.body, { practice: null, callId: 'CALL-3500', overall: 92, hurt: ['The call ended without a closing question'], helped: ["Acknowledged the customer's feelings"], hungUp: false, unresolved: false });   // only what protected points
  }
});

test('a scenario call starts with the scenario\'s own words, and the advisor agent reads the conversation and the scenario', async () => {
  const karim = await client(real, 'karim');
  const html = (await karim.get('/advisor').query({ scenario: 'sc_abc' }).expect(200)).text;
  assert.match(html, /data-scenario="sc_abc"/);
  assert.match(html, /opens with the scenario(&#39;|')s own words/);
  const token = tokenOf(html);
  const start = { persona: 'IMPATIENT', difficulty: 'MEDIUM', intent: 'BILLING', memory: false };
  const r = await karim.post('/advisor/live/start').set('X-CSRF-Token', token).send({ ...start, scenario: 'sc_abc' }).expect(200);
  assert.equal(r.body.opening, 'I lost my phone.');
  assert.deepEqual([calls.at(-1)?.opening, calls.at(-1)?.topic], ['I lost my phone.', 'my lost SIM']);
  await karim.post('/advisor/live/start').set('X-CSRF-Token', token).send({ ...start, scenario: 'nope' }).expect(200);
  assert.equal(calls.at(-1)?.opening, undefined, 'a scenario that is gone leaves a plain call');

  const turns = [{ speaker: 'customer', text: 'I lost my phone.', mood: 40 }, { speaker: 'nobody', text: 'dropped' }];
  await karim.post('/advisor/live/auto').set('X-CSRF-Token', token).send({ topic: 'I lost my phone.', turn: 1, turns, steps: ['acknowledge', 7], scenario: 'sc_abc' }).expect(200);
  assert.deepEqual(contexts.at(-1), { turns: [turns[0]], steps: ['acknowledge'], brief: 'You lost your phone. The customer is abroad.' });
});

test('the advisor agent\'s call is not filed under the person watching, and a practice call goes to the coach', async () => {
  const id = '0123456789abcdef', rim = await client(real, 'rim');
  const token = tokenOf((await rim.get('/advisor')).text);
  await rim.post('/advisor/live/review').set('X-CSRF-Token', token).send({ id, auto: true, scenario: 'sc_abc' }).expect(200);
  assert.deepEqual(reviewed.at(-1), ['review', 'Advisor agent', 'automatic']);
  const r = await rim.post('/advisor/live/review').set('X-CSRF-Token', token).send({ id, scenario: 'sc_abc' }).expect(200);
  assert.deepEqual(reviewed.find((x) => x[0] === 'practice'), ['practice', 'sc_abc', 'Rim']);
  assert.equal(r.body.practice.next, 'harder');
});

test('the coach sees the practice results, with the next step they call for', async () => {
  const rim = await client(real, 'rim');
  const html = (await rim.get('/training').query({ advisor: 'Hela M.' }).expect(200)).text;
  assert.match(html, /Practice results for Hela M\./);
  assert.match(html, /1 practice call · best 88\/100/);
  assert.match(html, /Compliance 5.1 to 9/);
  assert.match(html, /Passed at 88\/100/);
  assert.match(html, /Make it harder/);
  assert.match((await rim.get('/training').query({ advisor: 'Sami R.' }).expect(200)).text, /No practice yet/);
});
