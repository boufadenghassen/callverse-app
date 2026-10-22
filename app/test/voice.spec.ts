import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer, Server } from 'node:http';
import { NestExpressApplication } from '@nestjs/platform-express';
import { Test } from '@nestjs/testing';
import { AgentDownError, AgentGateway, BadAudioError, VoiceUnavailableError } from '../src/agents/agent.gateway';
import { MockAgentGateway } from '../src/agents/mock.gateway';
import { AppModule } from '../src/app.module';
import { setup } from '../src/setup';
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

const wav = (n = 400) => Buffer.concat([Buffer.from('RIFF'), Buffer.alloc(n)]);

test('voice notes: demo mode cannot transcribe (503), and bad uploads are refused', async () => {
  const karim = await client(app, 'karim'), token = await tokenOf(karim);
  const up = (body: Buffer) => karim.post('/voice/transcribe').set('Content-Type', 'audio/wav').set('X-CSRF-Token', token).send(body);
  assert.match((await up(wav()).expect(503)).body.error, /speech-to-text/);
  await up(Buffer.alloc(10)).expect(400);
  await karim.post('/voice/transcribe').set('Content-Type', 'audio/wav').send(wav()).expect(403);
  await (await client(app)).post('/voice/transcribe').set('Content-Type', 'audio/wav').send(wav()).expect(403);
});

test('the http gateway sends voice notes to the Python agents and maps their answers', async () => {
  const fake: Server = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => {
      const body = Buffer.concat(chunks).toString();
      res.setHeader('Content-Type', 'application/json');
      if (body.includes('silent')) { res.statusCode = 400; return res.end('{"detail":"I could not hear anything."}'); }
      if (body.includes('nomodel')) { res.statusCode = 503; return res.end('{}'); }
      res.end('{"text":"I will check the policy.","seconds":2.4}');
    });
  });
  await new Promise<void>((ok) => fake.listen(0, ok));
  process.env.CALLVERSE_AGENTS_URL = `http://localhost:${(fake.address() as { port: number }).port}`;
  try {
    const gw = new HttpAgentGateway();
    assert.deepEqual(await gw.transcribe(Buffer.from('RIFFok')), { text: 'I will check the policy.', seconds: 2.4 });
    await assert.rejects(() => gw.transcribe(Buffer.from('silent')), (e: Error) => e instanceof BadAudioError && /could not hear/.test(e.message));
    await assert.rejects(() => gw.transcribe(Buffer.from('nomodel')), VoiceUnavailableError);
  } finally {
    delete process.env.CALLVERSE_AGENTS_URL;
    fake.close();
  }
});

test('a voice note is also heard by the emotion model: the answer carries the tone, or null when that service is down', async () => {
  class Hearing extends MockAgentGateway { async transcribe() { return { text: 'Thank you very much.', seconds: 2 }; } }
  const moduleRef = await Test.createTestingModule({ imports: [AppModule] }).overrideProvider(AgentGateway).useValue(new Hearing()).compile();
  const hearing = moduleRef.createNestApplication<NestExpressApplication>();
  setup(hearing);
  await hearing.init();
  const emotion = createServer((req, res) => { res.setHeader('Content-Type', 'application/json'); res.end(req.url === '/emotion/analyze' ? JSON.stringify({ emotion: 'anger', mood: 14.4, confidence: 0.9 }) : '{}'); });
  await new Promise<void>((ok) => emotion.listen(0, ok));
  const was = process.env.CALLVERSE_EMOTION_URL;
  try {
    const karim = await client(hearing, 'karim'), token = /name="csrf-token" content="([^"]+)"/.exec((await karim.get('/advisor')).text)![1];
    const send = () => karim.post('/voice/transcribe').set('Content-Type', 'audio/wav').set('X-CSRF-Token', token).send(Buffer.alloc(2000, 1));
    process.env.CALLVERSE_EMOTION_URL = `http://localhost:${(emotion.address() as { port: number }).port}`;
    assert.deepEqual((await send().expect(200)).body, { text: 'Thank you very much.', seconds: 2, tone: { emotion: 'anger', mood: 14 } });
    process.env.CALLVERSE_EMOTION_URL = 'http://localhost:1';                                      // the service is not running: the words still count
    assert.deepEqual((await send().expect(200)).body, { text: 'Thank you very much.', seconds: 2, tone: null });
  } finally {
    if (was === undefined) delete process.env.CALLVERSE_EMOTION_URL; else process.env.CALLVERSE_EMOTION_URL = was;
    emotion.close();
    await hearing.close();
  }
});
