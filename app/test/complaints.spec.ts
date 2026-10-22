import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { HttpAgentGateway } from '../src/agents/http.gateway';
import { client, startApp } from './helpers';

test('the http gateway reads the open complaints and the root causes from the Python complaint agent', async () => {
  const seen: string[] = [];
  const fake = createServer((req, res) => {
    seen.push(`${req.method} ${req.url}`);
    res.setHeader('Content-Type', 'application/json');
    res.end(req.url!.startsWith('/complaints/cases')
      ? '[{"id":"CMP-1","summary":"Charged twice","severity":"Critical","escalationRisk":88,"cluster":"Billing and fees","hoursLeft":0,"overdue":true,"reasons":["Money is at stake (+15)"]}]'
      : '{"topics":[{"topic":"Billing and fees","cases":10,"open":2,"share":50,"unresolvedPct":20,"trendPct":null,"byMonth":{},"hotspots":[],"keywords":["bill"],"example":"x"}],"discovered":[]}');
  });
  await new Promise<void>((ok) => fake.listen(0, ok));
  process.env.CALLVERSE_AGENTS_URL = `http://localhost:${(fake.address() as { port: number }).port}`;
  try {
    const gw = new HttpAgentGateway();
    const cases = await gw.openComplaints();
    assert.equal(cases[0].reasons?.[0], 'Money is at stake (+15)');
    assert.equal((await gw.complaintClusters()).topics[0].topic, 'Billing and fees');
    assert.deepEqual(seen, ['GET /complaints/cases?limit=30', 'GET /complaints/clusters']);
  } finally {
    delete process.env.CALLVERSE_AGENTS_URL;
    fake.close();
  }
});

test('the complaints page shows the early warning, the lanes and the root causes (demo data)', async () => {
  const app = await startApp();
  try {
    const amine = await client(app, 'amine');
    const html = (await amine.get('/complaints').expect(200)).text;
    assert.match(html, /Early warning/);
    assert.match(html, /CMP-221/);
    assert.match(html, /Recurring root causes/);
    assert.match(html, /Billing duplicates/);
    assert.match(html, /n\/a|\+57%/);
  } finally {
    await app.close();
  }
});
