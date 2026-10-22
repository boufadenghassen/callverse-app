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
class FakeGateway extends MockAgentGateway {
  async scenario(id: string) { if (id === 'nope') throw new Error('Unknown scenario'); return id === 'SC-31' ? super.scenario(id) : { ...REAL, id }; }
  async autoReply(topic: string, turn: number, style: 'careful' | 'rushed'): Promise<m.AutoReply> {
    asked.push({ topic, turn, style });
    return { text: 'I am sorry about this.', step: 'acknowledge', turn, last: false, sources: ['Billing policy §4.2'], intents: ['Billing'], policyWarning: null, style };
  }
  async reviewCall(callId: string, advisor: string): Promise<m.QualityReview> {
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
    assert.deepEqual(r.body, { callId: 'CALL-3500', overall: 92, hurt: ['The call ended without a closing question'], helped: ["Acknowledged the customer's feelings"], hungUp: false, unresolved: false });   // only what protected points
  }
});
