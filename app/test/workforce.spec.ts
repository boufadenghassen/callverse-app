import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { NestExpressApplication } from '@nestjs/platform-express';
import { AgentDownError } from '../src/agents/agent.gateway';
import { HttpAgentGateway } from '../src/agents/http.gateway';
import { client, startApp } from './helpers';

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
});

test('the http gateway fetches the routing plan from the Python workforce agent', async () => {
  const fake = createServer((req, res) => {
    res.setHeader('Content-Type', 'application/json');
    res.end(req.url === '/workforce/routing' ? '{"baselineSla":0.68,"optimizedSla":0.72,"moves":3,"hours":[],"method":"Local search"}' : '{}');
  });
  await new Promise<void>((ok) => fake.listen(0, ok));
  process.env.CALLVERSE_AGENTS_URL = `http://localhost:${(fake.address() as { port: number }).port}`;
  try {
    const plan = await new HttpAgentGateway().routing();
    assert.equal(plan.optimizedSla, 0.72);
    assert.equal(plan.moves, 3);
  } finally {
    delete process.env.CALLVERSE_AGENTS_URL;
    fake.close();
  }
});
