import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer, Server } from 'node:http';
import { NestExpressApplication } from '@nestjs/platform-express';
import { AgentDownError, CustomerNotFoundError, UnknownCallError } from '../src/agents/agent.gateway';
import { HttpAgentGateway } from '../src/agents/http.gateway';
import { client, startApp } from './helpers';

let app: NestExpressApplication;
before(async () => { app = await startApp(); });
after(async () => { await app.close(); });

const tokenOf = async (agent: Awaited<ReturnType<typeof client>>) => /data-csrf="([^"]+)"/.exec((await agent.get('/advisor')).text)![1];
const start = { persona: 'ANGRY_PREMIUM', difficulty: 'HARD', intent: 'BILLING', memory: false };

test('the advisor console offers the live call', async () => {
  const html = (await (await client(app, 'karim')).get('/advisor').expect(200)).text;
  assert.match(html, /Live call with a simulated customer/);
  assert.match(html, /Angry premium client/);
});

test('a live call: the customer answers, the advisor agent suggests, the call ends with an outcome', async () => {
  const karim = await client(app, 'karim'), token = await tokenOf(karim);
  const post = (path: string, body: object) => karim.post(path).set('X-CSRF-Token', token).send(body);
  const s = (await post('/advisor/live/start', start).expect(200)).body;
  assert.match(s.id, /^[0-9a-f]{16}$/);
  assert.match(s.opening, /charged twice/);
  assert.ok(s.suggestion.text && s.suggestion.sources.length);

  const a = (await post('/advisor/live/say', { id: s.id, text: "I'm so sorry, I understand how frustrating this is." }).expect(200)).body;
  assert.equal(a.move, 'EMPATHY');
  assert.ok(a.mood > 35 && a.client && !a.ended);
  const done = (await post('/advisor/live/say', { id: s.id, text: 'I will send you a confirmation by email.' }).expect(200)).body;
  assert.equal(done.ended, true);
  assert.ok(done.outcome.verdict);
  const after = (await post('/advisor/live/say', { id: s.id, text: 'hello?' }).expect(200)).body;
  assert.equal(after.ended, true);
  assert.equal(after.suggestion, null);
});

test('the live call refuses bad input, other roles and missing CSRF tokens', async () => {
  const karim = await client(app, 'karim'), token = await tokenOf(karim);
  const post = (path: string, body: object) => karim.post(path).set('X-CSRF-Token', token).send(body);
  await post('/advisor/live/start', { ...start, persona: 'CONSTRUCTOR' }).expect(400);
  await post('/advisor/live/start', { ...start, persona: '__proto__' }).expect(400);
  await post('/advisor/live/say', { id: '../etc', text: 'hi' }).expect(400);
  await post('/advisor/live/say', { id: '0123456789abcdef', text: 'x'.repeat(301) }).expect(400);
  assert.equal((await post('/advisor/live/say', { id: '0123456789abcdef', text: 'hi' }).expect(404)).body.error.includes('lost'), true);
  await karim.post('/advisor/live/start').send(start).expect(403);
  const nour = await client(app, 'nour');
  const nourToken = /data-csrf="([^"]+)"/.exec((await nour.get('/call-review')).text)![1];
  await nour.post('/advisor/live/start').set('X-CSRF-Token', nourToken).send(start).expect(403);
});

test('the http gateway sends the real calls to the Python agents and maps their errors', async () => {
  const seen: string[] = [];
  const fake: Server = createServer((req, res) => {
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => {
      seen.push(`${req.method} ${req.url} ${body}`);
      res.setHeader('Content-Type', 'application/json');
      if (req.url!.endsWith('/gone/say')) { res.statusCode = 404; return res.end('{}'); }
      if (req.url === '/advisor/customers/ZZ-0000') { res.statusCode = 404; return res.end('{}'); }
      res.end(JSON.stringify({ id: 'x', persona: 'p', opening: 'o', mood: 1, patience: 2 }));
    });
  });
  await new Promise<void>((ok) => fake.listen(0, ok));
  process.env.CALLVERSE_AGENTS_URL = `http://localhost:${(fake.address() as { port: number }).port}`;
  try {
    const gw = new HttpAgentGateway();
    await gw.startCall({ persona: 'IMPATIENT', mix: null, difficulty: 'EASY', intent: 'BILLING', memory: false });
    await gw.suggestAnswer('YT-1042', 'double charge');
    assert.match(seen[0], /POST \/customer\/sessions \{"persona":"IMPATIENT"/);
    assert.match(seen[1], /POST \/advisor\/suggest \{"customer_id":"YT-1042","query":"double charge"\}/);
    await assert.rejects(() => gw.say('gone', 'hi'), UnknownCallError);
    await gw.customerContext('YT-1042');
    assert.equal(seen.length, 4);
    assert.match(seen[3], /GET \/advisor\/customers\/YT-1042/);
    await assert.rejects(() => gw.customerContext('ZZ-0000'), CustomerNotFoundError);
    process.env.CALLVERSE_AGENTS_URL = 'http://localhost:1';
    await assert.rejects(() => new HttpAgentGateway().startCall({ persona: 'IMPATIENT', mix: null, difficulty: 'EASY', intent: 'BILLING', memory: false }), AgentDownError);
  } finally {
    delete process.env.CALLVERSE_AGENTS_URL;
    fake.close();
  }
});

test("a voice note's tone reaches the customer; a tone that is not valid is ignored", async () => {
  const karim = await client(app, 'karim'), token = await tokenOf(karim);
  const post = (path: string, body: object) => karim.post(path).set('X-CSRF-Token', token).send(body);
  const call = async () => (await post('/advisor/live/start', start).expect(200)).body.id as string;
  const words = 'I am sorry about that, I understand.';
  const calm = (await post('/advisor/live/say', { id: await call(), text: words }).expect(200)).body;
  const shouted = (await post('/advisor/live/say', { id: await call(), text: words, tone: { emotion: 'anger', mood: 12 } }).expect(200)).body;
  assert.equal(calm.moveLabel, 'Acknowledge the frustration and use her history');
  assert.equal(shouted.moveLabel, 'Raised your voice or was rude');
  assert.ok(shouted.mood < calm.mood);
  for (const tone of [{ emotion: 'furious', mood: 5 }, { emotion: 'anger', mood: 5.5 }, { emotion: 'anger', mood: 500 }, 'anger', []]) {
    assert.equal((await post('/advisor/live/say', { id: await call(), text: words, tone }).expect(200)).body.moveLabel, calm.moveLabel);
  }
});
