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

/** What the real complaint agent answers, shaped like its Python output, so the page and the routes can be tested without Python. */
const factor = (name: string, points: number, why: string): m.SalesFactor => ({ name, points, why });
const CASE: m.ComplaintCase = {
  id: 'CMP-221', summary: 'I was charged twice for 180 dinars on my September bill and this is the third time', severity: 'Critical', escalationRisk: 86, cluster: 'Billing duplicates', hoursLeft: 3,
  clusterKey: 'billing_duplicate', otherClusters: [], cause: 'Process', team: 'Billing', customerId: 'YT-1042', customer: 'Yasmine Toumi', status: 'open', assigned: null, channel: 'call', source: 'simulated',
  opened: '2026-10-22T03:00', severityScore: 51, computedLevel: 'Critical', overridden: false,
  severityFactors: [factor('Money at stake', 15, 'about 180 TND is disputed'), factor('Public exposure', 12, '“post this online”')],
  riskFactors: [factor('Starting point', 10, 'every complaint can escalate'), factor('Someone is on it', -8, 'taken by amine')],
  deadline: { slaHours: 12, ageHours: 9, hoursLeft: 3, used: 0.75, overdue: false }, contacts: 2, amount: 180, warning: { why: 'escalation risk 86', hoursLeft: 3, alerted: false },
  actions: [{ action: 'Check the billing history, refund the duplicate and confirm it in writing.', why: 'the usual first step', who: 'Billing' }],
};
const LATE: m.ComplaintCase = { ...CASE, id: 'CMP-225', summary: 'An advisor was rude to me', severity: 'High', escalationRisk: 54, cluster: 'Advisor conduct', hoursLeft: -6, status: 'taken', assigned: 'sami', customerId: null, customer: null,
  warning: { why: '6 h past its deadline', hoursLeft: -6, alerted: true }, deadline: { slaHours: 24, ageHours: 30, hoursLeft: -6, used: 1.25, overdue: true }, overridden: true };
const DETAIL: m.ComplaintDetail = {
  ...CASE, text: 'I was charged twice for 180 dinars on my September bill and this is the third time I contact you about it.', events: [{ at: '2026-10-22T03:00', who: 'system', kind: 'opened', note: 'call, simulated' }],
  earlier: [{ id: 'CMP-190', summary: 'Charged twice in August', opened: '2026-10-02T18:48', status: 'closed' }], similar: [{ id: 'CMP-102', summary: 'Duplicate payment', resolution: 'Refund or credit given' }],
  worked: { code: 'refunded', label: 'Refund or credit given', count: 4, of: 5 }, resolution: null, trusted: null, callId: null,
  customerFile: { id: 'YT-1042', name: 'Yasmine Toumi', profile: 'Loyal customer, 6 years', contract: 'Mobile Plus 40 GB', openTickets: 1, transfers: 1, mood: 'Impatient', tenureYears: 6, monthlyTnd: 42, usageTrend: 5 },
};
const RESOLVED: m.ComplaintDetail = { ...DETAIL, id: 'CMP-228', status: 'resolved', resolution: 'Refund or credit given', warning: null };
const INSIGHTS: m.ComplaintInsights = {
  open: 2, byLevel: { Critical: 1, High: 1, Medium: 0, Low: 0 }, avgRisk: 70, overdue: 1, warnings: 2, followUps: 1, resolved: 40, avgResolutionHours: 45.9, slaMetRate: 0.78, trustRate: 0.86, reopened: 5, repeatRate: 0.54,
  weeks: [6, 2, 7, 6, 6, 5, 5, 9], simulated: 46, method: 'The history is simulated.', causes: [{ cause: 'Process', cases: 14, share: 0.3 }],
  clusters: [{ key: 'roaming', label: 'Roaming activation', cause: 'Tools', open: 1, last28: 7, previous28: 5, trend: 2, avgHours: 31.5, worked: { label: 'Refund or credit given', count: 5, of: 11 } }],
};
const seen: { acts: { id: string; act: m.ComplaintAct }[]; triage: { text: string; customerId: string | null }[]; created: { text: string; customerId: string | null; channel: string }[]; fromCalls: string[] } = { acts: [], triage: [], created: [], fromCalls: [] };

class FakeComplaintsGateway extends MockAgentGateway {
  async openComplaints() { return [CASE, LATE]; }
  async complaint(id: string) {
    if (id === 'CMP-999') throw new RejectedError('No such case.');
    return id === 'CMP-228' ? RESOLVED : { ...DETAIL, id };
  }
  async complaintTriage(text: string, customerId: string | null) { seen.triage.push({ text, customerId }); return { ...CASE, id: 'NEW' }; }
  async complaintCreate(text: string, customerId: string | null, channel: string) { seen.created.push({ text, customerId, channel }); return { ...DETAIL, id: 'CMP-300' }; }
  async complaintAct(id: string, act: m.ComplaintAct) {
    seen.acts.push({ id, act });
    if (act.note === 'refuse me') throw new RejectedError('Only an open case can be resolved.');
    return { ...DETAIL, id };
  }
  async complaintInsights() { return INSIGHTS; }
  async complaintFollowUps(): Promise<m.ComplaintFollowUp[]> { return [{ id: 'CMP-228', summary: 'Duplicate payment of 60 dinars', customer: 'YT-1042', resolution: 'Refund or credit given', due: '2026-10-25T10:00', dueInHours: 40 }]; }
  async complaintCandidates(): Promise<m.ComplaintCandidate[]> {
    return [{ callId: 'CALL-3331', advisor: 'Sami R.', overall: 61, why: ['the customer hung up', 'nothing was agreed'], text: 'My roaming bundle did not work abroad. This is the third time I call about it.', triage: { ...CASE, id: 'NEW', cluster: 'Roaming activation', severity: 'Medium', escalationRisk: 27 } }];
  }
  async complaintFromCall(callId: string) { seen.fromCalls.push(callId); return { ...DETAIL, id: 'CMP-301' }; }
}

let demo: NestExpressApplication, real: NestExpressApplication;
before(async () => {
  demo = await startApp();
  const moduleRef = await Test.createTestingModule({ imports: [AppModule] }).overrideProvider(AgentGateway).useValue(new FakeComplaintsGateway()).compile();
  real = moduleRef.createNestApplication<NestExpressApplication>();
  setup(real);
  await real.init();
});
after(async () => { await demo.close(); await real.close(); });

const tokenOf = (html: string) => /name="csrf-token" content="([^"]+)"/.exec(html)![1];
const form = async (agent: Awaited<ReturnType<typeof client>>, path: string, fields: Record<string, string>, from = '/complaints') => {
  const token = tokenOf((await agent.get(from)).text);
  return agent.post(path).type('form').send({ ...fields, _csrf: token });
};

test('only complaints (and admin) open the page; demo mode keeps its three demo lanes and no real-agent features', async () => {
  await (await client(demo, 'karim')).get('/complaints').expect(403);
  await (await client(demo)).get('/complaints').expect(302);
  const html = (await (await client(demo, 'amine')).get('/complaints').expect(200)).text;
  assert.match(html, /lane-critical/);
  assert.doesNotMatch(html, /Read a complaint|lane-low|Waiting for the follow-up/);
  await (await client(demo, 'amine')).get('/complaints/CMP-221').expect(404);                       // the demo data keeps no case file
});

test('with the real agent the page shows lanes with the reasons, the early warning, the follow-ups, the calls that may be complaints and where complaints come from', async () => {
  const html = (await (await client(real, 'amine')).get('/complaints').expect(200)).text;
  assert.match(html, /Real agent, invented cases and customers/);
  for (const lane of ['lane-critical', 'lane-high', 'lane-medium', 'lane-low']) assert.match(html, new RegExp(lane));
  assert.doesNotMatch(html, /draggable|data-escalate|data-lane/, 'the demo drag and drop is not offered on real cases');
  assert.match(html, /<strong>Early warning:<\/strong> <a href="\/complaints\/CMP-221">CMP-221<\/a>[^<]*: escalation risk 86\. Alert a supervisor now\./);
  assert.match(html, /action="\/complaints\/CMP-221\/alert"/);
  assert.match(html, /A supervisor was alerted\./);                                                    // the late case was alerted already
  assert.match(html, /<span class="eff pos">\+15<\/span>\s*<span><strong>Money at stake<\/strong>/);
  assert.match(html, /<span class="eff neg">−8<\/span>/);
  assert.match(html, /<strong class="late">6 h late<\/strong>/);
  assert.match(html, /taken by sami/);
  assert.match(html, /level set by hand/);
  assert.match(html, /action="\/complaints\/CMP-221\/take"/);
  assert.doesNotMatch(html, /action="\/complaints\/CMP-225\/take"/, 'a taken case cannot be taken again');
  assert.match(html, /Waiting for the follow-up call/);
  assert.match(html, /call in 40 h/);
  assert.match(html, /Calls that may be complaints[\s\S]*CALL-3331[\s\S]*the customer hung up; nothing was agreed/);
  assert.match(html, /action="\/complaints\/from-call"/);
  assert.match(html, /Where complaints come from[\s\S]*▲ \+2/);
  assert.match(html, /answered within the deadline/);
  assert.match(html, /Read a complaint/);
  assert.match(html, /data-tri-sample=/);
});

test('a case in full: the words, why this level and this risk, what to do first, the history, the log and the moves that fit its status', async () => {
  const nour = await client(real, 'amine');
  const html = (await nour.get('/complaints/CMP-221').expect(200)).text;
  assert.match(html, /What the customer said[\s\S]*charged twice for 180 dinars/);
  assert.match(html, /How serious: 51\/100/);
  assert.match(html, /How likely to escalate: 86\/100/);
  assert.match(html, /What to do first[\s\S]*refund the duplicate/);
  assert.match(html, /the usual outcome was <strong>refund or credit given<\/strong>: 4 of 5/);
  assert.match(html, /Yasmine Toumi[\s\S]*Mobile Plus 40 GB[\s\S]*Earlier cases[\s\S]*CMP-190/);
  assert.match(html, /<strong>opened<\/strong> by system/);
  assert.match(html, /action="\/complaints\/CMP-221\/resolve"/);
  assert.doesNotMatch(html, /action="\/complaints\/CMP-221\/close"/, 'only a resolved case is closed after its follow-up');
  const resolved = (await nour.get('/complaints/CMP-228').expect(200)).text;
  assert.match(resolved, /action="\/complaints\/CMP-228\/close"/);
  assert.match(resolved, /Follow-up call: is the customer satisfied\?/);
  await nour.get('/complaints/CMP-999').expect(404);
  await nour.get('/complaints/not-an-id').expect(404);
  await (await client(real, 'karim')).get('/complaints/CMP-221').expect(403);
});

test('a move on a case is a form: guarded, validated, done in the name of the signed-in user, and a refusal comes back with its message', async () => {
  const amine = await client(real, 'amine');
  await amine.post('/complaints/CMP-221/take').type('form').send({}).expect(403);                                         // no CSRF token
  assert.equal((await form(await client(real, 'karim'), '/complaints/CMP-221/take', {}, '/advisor')).status, 403);          // an advisor cannot act on complaints
  await form(amine, '/complaints/CMP-221/dance', {}).then((r) => assert.equal(r.status, 404));
  await form(amine, '/complaints/not-an-id/take', {}).then((r) => assert.equal(r.status, 404));
  const take = await form(amine, '/complaints/CMP-221/take', { back: 'list' });
  assert.equal(take.status, 302);
  assert.equal(take.headers.location, '/complaints');
  assert.deepEqual(seen.acts.at(-1), { id: 'CMP-221', act: { action: 'take', by: 'amine', note: '', resolution: undefined, level: undefined, trusted: undefined } });
  const noHow = await form(amine, '/complaints/CMP-221/resolve', { note: 'done' });
  assert.match(noHow.headers.location, /^\/complaints\/CMP-221\?error=Choose%20an%20answer/);
  const noAnswer = await form(amine, '/complaints/CMP-228/close', {});
  assert.match(noAnswer.headers.location, /\?error=/);
  const badLevel = await form(amine, '/complaints/CMP-221/severity', { level: 'Urgent' });
  assert.match(badLevel.headers.location, /\?error=/);
  const before = seen.acts.length;
  const resolve = await form(amine, '/complaints/CMP-221/resolve', { resolution: 'refunded', note: 'refunded 180\u0000 dinars' });
  assert.equal(resolve.headers.location, '/complaints/CMP-221');
  assert.deepEqual(seen.acts.at(-1)!.act, { action: 'resolve', by: 'amine', note: 'refunded 180  dinars', resolution: 'refunded', level: undefined, trusted: undefined });
  const close = await form(amine, '/complaints/CMP-228/close', { trusted: 'no', note: 'still waiting' });
  assert.equal(seen.acts.at(-1)!.act.trusted, false);
  assert.equal(close.headers.location, '/complaints/CMP-228');
  assert.equal(seen.acts.length, before + 2, 'the refused or incomplete moves never reached the agent');
  const refused = await form(amine, '/complaints/CMP-221/resolve', { resolution: 'fixed', note: 'refuse me' });
  assert.equal(refused.headers.location, '/complaints/CMP-221?error=Only%20an%20open%20case%20can%20be%20resolved.');
  const shown = (await amine.get(refused.headers.location).expect(200)).text;
  assert.match(shown, /<p class="warning" role="alert">Only an open case can be resolved\.<\/p>/);
});

test('reading a complaint, opening a case from it and from a call are validated; demo mode says it needs the real agents', async () => {
  const amine = await client(real, 'amine');
  const token = tokenOf((await amine.get('/complaints')).text);
  const triage = (b: object) => amine.post('/complaints/triage').set('X-CSRF-Token', token).send(b);
  await triage({ text: 'short' }).expect(400);
  await triage({ text: 'I was charged twice for 180 dinars.', customerId: 'not-an-id' }).expect(400);
  const ok = await triage({ text: 'I was charged twice for 180\u0000 dinars.', customerId: 'YT-1042' }).expect(200);
  assert.equal(ok.body.id, 'NEW');
  assert.deepEqual(seen.triage.at(-1), { text: 'I was charged twice for 180  dinars.', customerId: 'YT-1042' });
  await amine.post('/complaints/triage').send({ text: 'I was charged twice for 180 dinars.' }).expect(403);                  // no CSRF token
  const made = await form(amine, '/complaints/new', { text: 'My roaming pass did not work in Turkey.', customerId: 'IK-2210', channel: 'email' });
  assert.equal(made.headers.location, '/complaints/CMP-300');
  assert.deepEqual(seen.created.at(-1), { text: 'My roaming pass did not work in Turkey.', customerId: 'IK-2210', channel: 'email' });
  await form(amine, '/complaints/new', { text: 'My roaming pass did not work in Turkey.', channel: 'carrier-pigeon' });
  assert.equal(seen.created.at(-1)!.channel, 'call', 'an unknown channel falls back to a call');
  assert.match((await form(amine, '/complaints/new', { text: 'short' })).headers.location, /^\/complaints\?error=/);
  assert.equal((await form(amine, '/complaints/from-call', { callId: 'CALL-3331' })).headers.location, '/complaints/CMP-301');
  assert.equal(seen.fromCalls.at(-1), 'CALL-3331');
  assert.match((await form(amine, '/complaints/from-call', { callId: '../etc' })).headers.location, /^\/complaints\?error=/);
  const demoAmine = await client(demo, 'amine');
  const demoToken = tokenOf((await demoAmine.get('/complaints')).text);
  assert.match((await demoAmine.post('/complaints/triage').set('X-CSRF-Token', demoToken).send({ text: 'I was charged twice for 180 dinars.' }).expect(503)).body.error, /real agents/);
});

test('the http gateway reads the Python complaint agent and maps its refusals', async () => {
  const calls: string[] = [];
  const fake = createServer((req, res) => {
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => {
      calls.push(`${req.method} ${req.url} ${body}`);
      res.setHeader('Content-Type', 'application/json');
      if (req.url === '/complaints/CMP-999999') { res.statusCode = 404; return res.end('{"detail":"No such case."}'); }
      if (req.url?.endsWith('/resolve')) { res.statusCode = 422; return res.end('{"detail":"Choose how it was resolved."}'); }
      res.end(req.url === '/complaints/open' ? JSON.stringify([CASE]) : req.url === '/complaints/insights' ? JSON.stringify(INSIGHTS) : req.url === '/complaints/follow-ups' || req.url === '/complaints/from-calls' ? '[]' : JSON.stringify(DETAIL));
    });
  });
  await new Promise<void>((ok) => fake.listen(0, ok));
  const was = process.env.CALLVERSE_AGENTS_URL;
  process.env.CALLVERSE_AGENTS_URL = `http://localhost:${(fake.address() as { port: number }).port}`;
  try {
    const gw = new HttpAgentGateway();
    assert.equal((await gw.openComplaints())[0].severityFactors?.length, 2);
    assert.equal((await gw.complaintInsights())?.open, 2);
    assert.deepEqual(await gw.complaintFollowUps(), []);
    assert.deepEqual(await gw.complaintCandidates(), []);
    assert.equal((await gw.complaint('CMP-221')).id, 'CMP-221');
    await assert.rejects(() => gw.complaint('CMP-999999'), (e: Error) => e instanceof RejectedError && /No such case/.test(e.message));
    await gw.complaintTriage('I was charged twice for 180 dinars.', 'YT-1042');
    assert.equal(calls.at(-1), 'POST /complaints/triage {"text":"I was charged twice for 180 dinars.","customer_id":"YT-1042"}');
    await gw.complaintCreate('My roaming pass did not work.', null, 'email');
    assert.equal(calls.at(-1), 'POST /complaints {"text":"My roaming pass did not work.","customer_id":null,"channel":"email"}');
    await gw.complaintFromCall('CALL-3331');
    assert.equal(calls.at(-1), 'POST /complaints/from-call {"call_id":"CALL-3331"}');
    await gw.complaintAct('CMP-221', { action: 'take', by: 'amine' });
    assert.equal(calls.at(-1), 'POST /complaints/CMP-221/take {"by":"amine","note":"","resolution":null,"level":null,"trusted":null}');
    await assert.rejects(() => gw.complaintAct('CMP-221', { action: 'resolve', by: 'amine' }), (e: Error) => e instanceof RejectedError && /Choose how/.test(e.message));
    process.env.CALLVERSE_AGENTS_URL = 'http://localhost:1';
    await assert.rejects(() => new HttpAgentGateway().openComplaints(), AgentDownError);
  } finally {
    if (was === undefined) delete process.env.CALLVERSE_AGENTS_URL; else process.env.CALLVERSE_AGENTS_URL = was;
    fake.close();
  }
});
