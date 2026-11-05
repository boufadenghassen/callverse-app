import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer, Server } from 'node:http';
import { NestExpressApplication } from '@nestjs/platform-express';
import { client, startApp } from './helpers';

let app: NestExpressApplication, fake: Server;
before(async () => {
  app = await startApp();
  fake = createServer((req, res) => {          // stands in for models/src/serve.py
    req.resume();
    res.setHeader('Content-Type', 'application/json');
    const explanation = { method: 'occlusion', target: 'anger', blockSec: 0.5, blocks: [{ startSec: 0, endSec: 0.5, drop: 0.08, rel: 1 }, { startSec: 0.5, endSec: 1, drop: -0.01, rel: -0.1 }], top: [{ startSec: 0, endSec: 0.5, drop: 0.08 }] };
    res.end(JSON.stringify({ emotion: 'anger', confidence: 0.9, mood: 12, durationSec: 2, probabilities: { anger: 0.9 }, timeline: [], explanation }));
  });
  await new Promise<void>((ok) => fake.listen(0, ok));
});
after(async () => { fake.close(); await app.close(); });

test('only quality (and admin) open the call review page', async () => {
  await (await client(app, 'karim')).get('/call-review').expect(403);
  const page = (await (await client(app, 'nour')).get('/call-review').expect(200)).text;
  assert.match(page, /Analyze emotion/);
  assert.match(page, /Why this answer/);        // the explanation section is part of the page (hidden until a result arrives)
});

test('an upload is scored by the emotion service, and needs the CSRF header', async () => {
  const nour = await client(app, 'nour');
  await nour.post('/call-review/analyze').set('Content-Type', 'application/octet-stream').send(Buffer.from('x')).expect(403);
  const token = /data-csrf="([^"]+)"/.exec((await nour.get('/call-review')).text)![1];
  process.env.CALLVERSE_EMOTION_URL = `http://localhost:${(fake.address() as { port: number }).port}`;
  const ok = await nour.post('/call-review/analyze').set('Content-Type', 'application/octet-stream').set('X-CSRF-Token', token).send(Buffer.from('RIFFfake')).expect(200);
  assert.equal(ok.body.emotion, 'anger');
  assert.equal(ok.body.explanation.method, 'occlusion');           // the explanation goes through untouched
  process.env.CALLVERSE_EMOTION_URL = 'http://localhost:1';
  const down = await nour.post('/call-review/analyze').set('Content-Type', 'application/octet-stream').set('X-CSRF-Token', token).send(Buffer.from('RIFFfake')).expect(503);
  assert.match(down.body.error, /not running/);
});
