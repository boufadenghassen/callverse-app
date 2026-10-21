import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer, Server } from 'node:http';
import { NestExpressApplication } from '@nestjs/platform-express';
import { AgentDownError, BadAudioError, UnknownCallError, VoiceUnavailableError } from '../src/agents/agent.gateway';
import { HttpAgentGateway } from '../src/agents/http.gateway';
import { qualityView, sparkline } from '../src/pages/charts';
import { QualityReview } from '../src/agents/models';
import { client, startApp } from './helpers';

let app: NestExpressApplication;
before(async () => { app = await startApp(); });
after(async () => { await app.close(); });

const tokenOf = async (agent: Awaited<ReturnType<typeof client>>, path = '/quality') => /name="csrf-token" content="([^"]+)"/.exec((await agent.get(path)).text)![1];
const wav = Buffer.concat([Buffer.from('RIFF'), Buffer.alloc(400)]);

test('the quality page shows team analytics, a way to review a call and the reviews', async () => {
  const html = (await (await client(app, 'nour')).get('/quality').expect(200)).text;
  assert.match(html, /Team analytics/);
  assert.match(html, /Review a call/);
  assert.match(html, /Download a sample call/);
  assert.match(html, /CALL-3381/);
  assert.doesNotMatch(html, /style="/, 'no inline styles: the content security policy would block them');
});

test('only quality (and admin) open the quality page; the advisor does not', async () => {
  await (await client(app, 'karim')).get('/quality').expect(403);
  await (await client(app)).get('/quality').expect(302);
});

test('a focus on one call and a filter by advisor are validated, not trusted', async () => {
  const nour = await client(app, 'nour');
  await nour.get('/quality').query({ call: '<script>', advisor: 'x'.repeat(500) }).expect(200);
  const html = (await nour.get('/quality').query({ call: 'CALL-3379' })).text;
  assert.ok(html.indexOf('CALL-3379') < html.indexOf('CALL-3381'), 'the focused call comes first');
});

test('demo mode cannot review recordings or live calls and says so (503), with the right guards', async () => {
  const nour = await client(app, 'nour'), token = await tokenOf(nour);
  const up = (body: Buffer) => nour.post('/quality/audio').query({ advisor: 'Karim B.' }).set('Content-Type', 'audio/wav').set('X-CSRF-Token', token).send(body);
  assert.match((await up(wav).expect(503)).body.error, /real agents/);
  assert.match((await up(Buffer.alloc(10)).expect(400)).body.error, /Choose a recording/);
  await nour.post('/quality/audio').set('Content-Type', 'audio/wav').send(wav).expect(403);                              // no CSRF token
  const karim = await client(app, 'karim'), kt = await tokenOf(karim, '/advisor');
  await karim.post('/quality/audio').set('Content-Type', 'audio/wav').set('X-CSRF-Token', kt).send(wav).expect(403);      // an advisor cannot review recordings
  const review = (id: string) => karim.post('/advisor/live/review').set('X-CSRF-Token', kt).send({ id });
  assert.match((await review('0123456789abcdef').expect(503)).body.error, /real agents/);
  await review('../etc').expect(400);
  await nour.post('/advisor/live/review').set('X-CSRF-Token', token).send({ id: '0123456789abcdef' }).expect(403);       // quality does not send calls to itself
  await nour.get('/quality/sample-call.wav').expect(503);
});

test('the review view builds a timeline, a mood curve and a transcript with its flags', () => {
  const review: QualityReview = {
    callId: 'CALL-1', advisor: 'A.', overall: 50, counterfactual: '', durationSec: 95, moodSource: 'given', source: 'recording',
    criteria: [{ name: 'Compliance', score: 4, max: 10, evidence: 'x', timestamp: '00:35' }],
    turns: [{ speaker: 'customer', text: 'hi', start: 0, end: 3, mood: 40, emotion: 'sad', flags: [] }, { speaker: 'advisor', text: 'hello', start: 5, end: 8, mood: null, emotion: null, flags: ['no_empathy'] }],
    errors: [{ rule: 'no_empathy', criterion: 'Communication', points: 3, turn: 1, timestamp: '00:05', quote: 'hello', reason: 'No empathy', fix: 'x', cause: 'Soft skills' }],
    strengths: [{ turn: 1, timestamp: '00:05', text: 'Greeted', rule: 'greeting' }], moodCurve: [[0, 40]],
  };
  const v = qualityView(review);
  assert.equal(v.length, '2:00');                                   // 95 s + margin, rounded up to half minutes
  assert.equal(v.turns[1].errors.length, 1);
  assert.equal(v.turns[1].strengths[0].text, 'Greeted');
  assert.equal(v.turns[0].errors.length, 0);
  assert.match(v.curve, /^\d+\.\d,\d+\.\d$/);
  assert.match(v.moodNote, /emotion model/);
  assert.match(qualityView({ ...review, source: 'live call' }).moodNote, /simulator/);
  assert.match(qualityView({ ...review, moodSource: 'text' }).moodNote, /word list/);
});

test('the sparkline scales around the data, leaves gaps for missing weeks and copes with nothing', () => {
  assert.deepEqual(sparkline([null, null]), []);
  const lines = sparkline([70, 72, null, 90, 91], 100, 30);
  assert.equal(lines.length, 2, 'a gap splits the line');
  const ys = lines.flatMap((l) => l.split(' ').map((p) => Number(p.split(',')[1])));
  assert.ok(Math.max(...ys) - Math.min(...ys) > 15, 'a change of 20 points uses most of the height');
  assert.equal(sparkline([80], 100, 30).length, 1);
});

test('the http gateway talks to the Python quality agent and maps its answers', async () => {
  const seen: string[] = [];
  const fake: Server = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => {
      const body = Buffer.concat(chunks).toString();
      seen.push(`${req.method} ${req.url}`);
      const json = (status: number, data: unknown) => { res.statusCode = status; res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(data)); };
      if (req.url!.startsWith('/quality/reviews/CALL-0000')) return json(404, {});
      if (req.url!.startsWith('/quality/reviews/')) return json(200, { callId: 'CALL-3385', advisor: 'A.', overall: 70, criteria: [], counterfactual: '' });
      if (req.url!.startsWith('/quality/reviews')) return json(200, []);
      if (req.url === '/quality/analytics') return json(200, { team: null, advisors: [], method: 'm' });
      if (req.url === '/quality/review-call') return body.includes('gone') ? json(404, {}) : body.includes('empty') ? json(400, { detail: 'Say something first.' }) : json(200, { callId: 'CALL-3386', overall: 61 });
      if (req.url!.startsWith('/quality/review-audio')) return body.includes('mono') ? json(422, { detail: 'Needs two channels.' }) : body.includes('nomodel') ? json(503, {}) : json(200, { callId: 'CALL-3387', overall: 55 });
      if (req.url === '/quality/sample-call.wav') { res.setHeader('Content-Type', 'audio/wav'); return res.end(Buffer.from('RIFFsample')); }
      json(404, {});
    });
  });
  await new Promise<void>((ok) => fake.listen(0, ok));
  process.env.CALLVERSE_AGENTS_URL = `http://localhost:${(fake.address() as { port: number }).port}`;
  try {
    const gw = new HttpAgentGateway();
    await gw.recentReviews('Karim B.');
    assert.equal(seen.at(-1), 'GET /quality/reviews?limit=20&advisor=Karim%20B.');
    await gw.recentReviews('a&limit=999');
    assert.match(seen.at(-1)!, /advisor=a%26limit%3D999$/, 'an advisor name cannot add query parameters');
    assert.equal(await gw.qualityReview('CALL-0000'), null);
    assert.equal((await gw.qualityReview('CALL-3385'))?.overall, 70);
    assert.equal((await gw.qualityAnalytics()).team, null);
    assert.equal((await gw.reviewCall('abc', 'A.')).overall, 61);
    await assert.rejects(() => gw.reviewCall('gone', 'A.'), UnknownCallError);
    await assert.rejects(() => gw.reviewCall('empty', 'A.'), (e: Error) => e instanceof BadAudioError && /Say something/.test(e.message));
    assert.equal((await gw.reviewAudio(Buffer.from('stereo'), 'A. B')).overall, 55);
    assert.match(seen.at(-1)!, /advisor=A\.%20B$/);
    await assert.rejects(() => gw.reviewAudio(Buffer.from('mono'), 'A.'), (e: Error) => e instanceof BadAudioError && /two channels/.test(e.message));
    await assert.rejects(() => gw.reviewAudio(Buffer.from('nomodel'), 'A.'), VoiceUnavailableError);
    assert.equal((await gw.sampleCall()).toString(), 'RIFFsample');
    process.env.CALLVERSE_AGENTS_URL = 'http://localhost:1';
    await assert.rejects(() => new HttpAgentGateway().qualityAnalytics(), AgentDownError);
  } finally {
    delete process.env.CALLVERSE_AGENTS_URL;
    fake.close();
  }
});
