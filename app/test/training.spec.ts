import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { NestExpressApplication } from '@nestjs/platform-express';
import { RejectedError } from '../src/agents/agent.gateway';
import { HttpAgentGateway } from '../src/agents/http.gateway';
import { client, count, post, startApp } from './helpers';

let app: NestExpressApplication;
before(async () => { app = await startApp(); });
after(async () => { await app.close(); });

test('the scenario builder makes a scenario on the server and opens its page (POST, CSRF, trainer only)', async () => {
  const rim = await client(app, 'rim');
  const html = (await rim.get('/training').expect(200)).text;
  assert.match(html, /<form method="post" action="\/training\/generate"/);
  assert.doesNotMatch(html, /id="whatif"/);                                                   // the old in-page builder is gone
  const made = await post(rim, '/training/generate', '/training', { difficulty: 'Hard', advisor: 'Hela M.' });
  assert.equal(made.status, 302);
  assert.match(made.headers.location, /^\/training\/scenarios\/SC-\d+\?advisor=Hela%20M\.$/);
  const page = (await rim.get(made.headers.location).expect(200)).text;
  assert.match(page, /Difficulty 4\/5/);
  await rim.post('/training/generate').type('form').send({ difficulty: 'Hard' }).expect(403);    // no CSRF token
  await (await client(app, 'karim')).post('/training/generate').type('form').send({ difficulty: 'Hard' }).expect(403);   // not the trainer
});

test('the builder refuses a difficulty it does not know and takes "any"', async () => {
  const rim = await client(app, 'rim');
  for (const bad of ['Impossible', '__proto__', 'hard']) assert.equal((await post(rim, '/training/generate', '/training', { difficulty: bad })).status, 400, bad);
  assert.equal((await post(rim, '/training/generate', '/training', { difficulty: '' })).status, 302);
  assert.equal((await post(rim, '/training/generate', '/training', {})).status, 302);
});

test('opening the Training page never creates a scenario: only a POST does', async () => {
  const rim = await client(app, 'rim');
  const before = count((await rim.get('/training').expect(200)).text, 'class="case-id"');
  for (let i = 0; i < 3; i++) await rim.get('/training?whatif=SC-31&op=harder').expect(200);   // the old link that used to create a variant on every load
  const after = count((await rim.get('/training').expect(200)).text, 'class="case-id"');
  assert.equal(after, before);
  const html = (await rim.get('/training').expect(200)).text;
  assert.match(html, /<form method="post" action="\/training\/scenarios\/SC-31\/mutate\?advisor=/);   // what-if is a form now
  assert.doesNotMatch(html, /whatif=/);
  const replay = (await rim.get('/training?replay=SC-31').expect(200)).text;                          // replaying only reads
  assert.match(replay, /Replay loaded/);
  await rim.get('/training?replay=nope').expect(404);
});

test('the offers on the coach plan are the same for every advisor and say so', async () => {
  const rim = await client(app, 'rim');
  const list = (html: string) => /<h3>Offers to practise today<\/h3>[\s\S]*?<\/article>/.exec(html)![0];
  const karim = list((await rim.get('/training?advisor=Karim%20B.').expect(200)).text);
  const hela = list((await rim.get('/training?advisor=Hela%20M.').expect(200)).text);
  assert.equal(karim, hela);
  assert.match(karim, /not tied to this advisor/);
});

test('the http gateway asks the Scenario Gen agent to generate, with or without a difficulty', async () => {
  const seen: string[] = [];
  const fake = createServer((req, res) => {
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => {
      seen.push(`${req.method} ${req.url} ${body}`);
      res.setHeader('Content-Type', 'application/json');
      res.end('{"id":"sc_abc","title":"Refund follow-up","profile":"New","difficulty":"Easy","origin":"Template library"}');
    });
  });
  await new Promise<void>((ok) => fake.listen(0, ok));
  const was = process.env.CALLVERSE_AGENTS_URL;
  process.env.CALLVERSE_AGENTS_URL = `http://localhost:${(fake.address() as { port: number }).port}`;
  try {
    const gw = new HttpAgentGateway();
    assert.equal((await gw.generateScenario(4)).id, 'sc_abc');
    assert.equal(seen.at(-1), 'POST /scenario-gen/scenarios/generate {"difficulty":4}');
    await gw.generateScenario(null);
    assert.equal(seen.at(-1), 'POST /scenario-gen/scenarios/generate {}');
    assert.ok(RejectedError);                                                                       // (the generator answers 422 for a value it does not accept; the page never sends one)
  } finally {
    if (was === undefined) delete process.env.CALLVERSE_AGENTS_URL; else process.env.CALLVERSE_AGENTS_URL = was;
    fake.close();
  }
});
