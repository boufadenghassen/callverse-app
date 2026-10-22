import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { NestExpressApplication } from '@nestjs/platform-express';
import { AgentDownError } from '../src/agents/agent.gateway';
import { HttpAgentGateway } from '../src/agents/http.gateway';
import { client, post, startApp } from './helpers';

let app: NestExpressApplication;
before(async () => { app = await startApp(); });
after(async () => { await app.close(); });

test('the http gateway asks the Python workforce agent for the forecast and the simulation', async () => {
  const seen: string[] = [];
  const fake = createServer((req, res) => {
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => {
      seen.push(`${req.method} ${req.url} ${body}`);
      res.setHeader('Content-Type', 'application/json');
      res.end(req.url!.startsWith('/workforce/forecast')
        ? '[{"hour":"9h","actual":23,"forecast":19}]'
        : '{"baselineWaitSec":98,"simulatedWaitSec":12,"baselineSla":0.58,"simulatedSla":0.89,"recommendations":["Add 2 advisors"],"hours":[],"method":"Erlang C"}');
    });
  });
  await new Promise<void>((ok) => fake.listen(0, ok));
  process.env.CALLVERSE_AGENTS_URL = `http://localhost:${(fake.address() as { port: number }).port}`;
  try {
    const gw = new HttpAgentGateway();
    assert.deepEqual(await gw.forecast('B'), [{ hour: '9h', actual: 23, forecast: 19 }]);
    await gw.forecast('B');                                       // the forecast is cached for 30 seconds: one request
    const r = await gw.simulate({ queue: 'B', extraAdvisors: 2, from: '14:00', to: '16:00' });
    assert.equal(r.simulatedSla, 0.89);
    assert.deepEqual(seen, ['GET /workforce/forecast?queue=B ', 'POST /workforce/simulate {"queue":"B","extraAdvisors":2,"from":"14:00","to":"16:00"}']);
    assert.equal((await gw.forecast('A/../x')).length, 1, 'a hostile queue name stays inside the query string');
    assert.match(seen[2], /queue=A%2F\.\.%2Fx/);
    process.env.CALLVERSE_AGENTS_URL = 'http://localhost:1';
    await assert.rejects(() => new HttpAgentGateway().simulate({ queue: 'B', extraAdvisors: 1, from: '14:00', to: '16:00' }), AgentDownError);
  } finally {
    delete process.env.CALLVERSE_AGENTS_URL;
    fake.close();
  }
});

test('the workforce page shows the routing and allocation plan with its moves', async () => {
  const html = (await (await client(app, 'sana')).get('/workforce').expect(200)).text;
  assert.match(html, /Routing and allocation/);
  assert.match(html, /Move C02/);
  assert.match(html, /Apply the moves/);
  assert.match(html, /Breaks and shifts/);
  assert.match(html, /Lunches spread out/);
});

test('the http gateway fetches the routing plan and the lunch schedule from the Python workforce agent', async () => {
  const seen: string[] = [];
  const fake = createServer((req, res) => {
    res.setHeader('Content-Type', 'application/json');
    seen.push(req.url!);
    res.end(req.url === '/workforce/routing' ? '{"baselineSla":0.68,"optimizedSla":0.72,"moves":3,"hours":[],"method":"Local search"}' : '{"plannedSla":0.85}');
  });

  await new Promise<void>((ok) => fake.listen(0, ok));
  process.env.CALLVERSE_AGENTS_URL = `http://localhost:${(fake.address() as { port: number }).port}`;
  try {
    const gw = new HttpAgentGateway();
    const plan = await gw.routing();
    assert.equal(plan.optimizedSla, 0.72);
    assert.equal(plan.moves, 3);
    assert.equal((await gw.schedule()).plannedSla, 0.85);
    assert.deepEqual(seen, ['/workforce/routing', '/workforce/schedule']);
  } finally {
    delete process.env.CALLVERSE_AGENTS_URL;
    fake.close();
  }
});

test('the http gateway fetches training scenarios from the Scenario Gen adapter', async () => {
  const seen: string[] = [];
  const fake = createServer((req, res) => {
    seen.push(`${req.method} ${req.url}`);
    res.setHeader('Content-Type', 'application/json');
    res.end('[{"id":"sc_1","title":"Double billing","profile":"Unsatisfied","difficulty":"Hard","origin":"Template library"}]');
  });

  await new Promise<void>((ok) => fake.listen(0, ok));
  process.env.CALLVERSE_AGENTS_URL = `http://localhost:${(fake.address() as { port: number }).port}`;
  try {
    const gw = new HttpAgentGateway();
    assert.deepEqual(await gw.scenarios(), [{
      id: 'sc_1', title: 'Double billing', profile: 'Unsatisfied', difficulty: 'Hard', origin: 'Template library',
    }]);
    await gw.scenarios();
    assert.deepEqual(seen, ['GET /training/scenarios']);
  } finally {
    delete process.env.CALLVERSE_AGENTS_URL;
    fake.close();
  }
});

test('the Coach training flow changes advisor data and supports scenario details, what-if, and delete', async () => {
  const coach = await client(app, 'rim');
  const karim = await coach.get('/training?advisor=Karim%20B.').expect(200);
  const hela = await coach.get('/training?advisor=Hela%20M.').expect(200);
  assert.match(karim.text, /Coach plan for Karim B\./);
  assert.match(karim.text, /Compliance/);
  assert.match(hela.text, /Coach plan for Hela M\./);
  assert.match(hela.text, /Accuracy/);

  await coach.get('/training/scenarios/SC-31').expect(200);
  const mutation = await post(coach, '/training/scenarios/SC-31/mutate', '/training/scenarios/SC-31', { op: 'harder' });
  assert.equal(mutation.status, 302);
  const mutatedPath = mutation.headers.location as string;
  await coach.get(mutatedPath).expect(200);
  const deleted = await post(coach, `${mutatedPath.split('?')[0]}/delete`, mutatedPath, {});
  assert.equal(deleted.status, 302);
  await coach.get(mutatedPath).expect(404);
});

test('the Coach generates scenarios only for the selected advisor and replays them through the server', async () => {
  const coach = await client(app, 'rim');
  const before = await coach.get('/training?advisor=Karim%20B.').expect(200);
  assert.match(before.text, /Generate targeted scenarios/);
  assert.doesNotMatch(before.text, /SC-hela/);

  const generated = await post(coach, '/training/scenarios/generate?advisor=Hela%20M.', '/training', { difficulty: 'Hard' });
  assert.equal(generated.status, 302);
  const generatedPath = generated.headers.location as string;
  assert.match(generatedPath, /training\/scenarios\//);
  const details = await coach.get(generatedPath).expect(200);
  assert.match(details.text, /Difficulty 4\/5/);

  const hela = await coach.get('/training?advisor=Hela%20M.').expect(200);
  assert.match(hela.text, /Hela M\./);
  assert.match(hela.text, /Replay/);
  const karim = await coach.get('/training?advisor=Karim%20B.').expect(200);
  assert.doesNotMatch(karim.text, new RegExp(generatedPath.split('?')[0].split('/').pop()!));

  const replayPath = `${generatedPath.split('?')[0]}/replay?advisor=Hela%20M.`;
  const replayed = await post(coach, replayPath, generatedPath, {});
  assert.equal(replayed.status, 302);
  assert.match(replayed.headers.location as string, /replayed=1/);
  await coach.get(replayed.headers.location as string).expect(200);
});

test('the Coach renders one scenario list and keeps generation and replay routes available', async () => {
  const coach = await client(app, 'rim');
  const before = await coach.get('/training?advisor=Hela%20M.').expect(200);
  assert.equal((before.text.match(/id="targeted-simulations"/g) ?? []).length, 1);
  assert.equal((before.text.match(/id="scenarios"/g) ?? []).length, 0);
  assert.match(before.text, /action="\/training\/scenarios\/generate\?advisor=Hela%20M\."/);

  const generated = await post(coach, '/training/scenarios/generate?advisor=Hela%20M.', '/training', { difficulty: 'Medium' });
  assert.equal(generated.status, 302);
  const generatedPath = generated.headers.location as string;
  const scenarioId = generatedPath.match(/\/training\/scenarios\/([^?]+)/)?.[1];
  assert.ok(scenarioId);

  const replayed = await post(coach, `/training/scenarios/${scenarioId}/replay?advisor=Hela%20M.`, generatedPath, {});
  assert.equal(replayed.status, 302);
  assert.match(replayed.headers.location as string, /replayed=1/);
});
