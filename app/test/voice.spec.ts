import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer, Server } from 'node:http';
import { NestExpressApplication } from '@nestjs/platform-express';
import { AgentDownError, VoiceUnavailableError } from '../src/agents/agent.gateway';
import { HttpAgentGateway } from '../src/agents/http.gateway';
import { client, startApp } from './helpers';

let app: NestExpressApplication;
before(async () => { app = await startApp(); });
after(async () => { await app.close(); });

const tokenOf = async (agent: Awaited<ReturnType<typeof client>>) => /name="csrf-token" content="([^"]+)"/.exec((await agent.get('/advisor')).text)![1];

test('every page carries the CSRF token the voice script needs', async () => {
  const karim = await client(app, 'karim');
  assert.ok((await tokenOf(karim)).length > 10);
});

test('demo mode has no neural voice: 503, so the page falls back to the browser voice', async () => {
  const karim = await client(app, 'karim'), token = await tokenOf(karim);
  const res = await karim.post('/voice/speak').set('X-CSRF-Token', token).send({ text: 'Hello there.', role: 'advisor' }).expect(503);
  assert.match(res.body.error, /No neural voice/);
});

test('the voice refuses empty or oversized text, a bad role, anonymous users and a missing token', async () => {
  const karim = await client(app, 'karim'), token = await tokenOf(karim);
  const post = (body: object) => karim.post('/voice/speak').set('X-CSRF-Token', token).send(body);
  await post({ text: '', role: 'advisor' }).expect(400);
  await post({ text: 'x'.repeat(401), role: 'advisor' }).expect(400);
  await post({ text: 'hi', role: 'robot' }).expect(400);
  await karim.post('/voice/speak').send({ text: 'hi', role: 'advisor' }).expect(403);
  await (await client(app)).post('/voice/speak').send({ text: 'hi', role: 'advisor' }).expect(403);
});

test('the http gateway fetches audio from the Python voice and maps its errors', async () => {
  const seen: string[] = [];
  const fake: Server = createServer((req, res) => {
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => {
      seen.push(`${req.method} ${req.url} ${body}`);
      if (body.includes('missing')) { res.statusCode = 503; return res.end('{}'); }
      res.setHeader('Content-Type', 'audio/wav');
      res.end(Buffer.from('RIFFfakewav'));
    });
  });
  await new Promise<void>((ok) => fake.listen(0, ok));
  process.env.CALLVERSE_AGENTS_URL = `http://localhost:${(fake.address() as { port: number }).port}`;
  try {
    const gw = new HttpAgentGateway();
    const audio = await gw.speak({ text: 'Hello', role: 'customer', persona: 'ANXIOUS', mood: 30 });
    assert.equal(audio.toString(), 'RIFFfakewav');
    assert.match(seen[0], /POST \/voice\/speak \{"text":"Hello","role":"customer","persona":"ANXIOUS","mood":30\}/);
    await assert.rejects(() => gw.speak({ text: 'missing', role: 'advisor', persona: null, mood: 50 }), VoiceUnavailableError);
    process.env.CALLVERSE_AGENTS_URL = 'http://localhost:1';
    await assert.rejects(() => new HttpAgentGateway().speak({ text: 'Hello', role: 'advisor', persona: null, mood: 50 }), AgentDownError);
  } finally {
    delete process.env.CALLVERSE_AGENTS_URL;
    fake.close();
  }
});
