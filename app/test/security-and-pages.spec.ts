import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { client, csrfOf, PASSWORD, post, startApp } from './helpers';

let app: NestExpressApplication;
before(async () => { app = await startApp(); });
after(async () => { await app.close(); });

test('anonymous users are sent to login', async () => {
  const res = await (await client(app)).get('/advisor');
  assert.equal(res.status, 302);
  assert.equal(res.headers.location, '/login');
});

test('an advisor sees their own workspace only', async () => {
  const karim = await client(app, 'karim');
  await karim.get('/advisor').expect(200);
  await karim.get('/workforce').expect(403);
});

test('security headers are present', async () => {
  const res = await (await client(app, 'karim')).get('/advisor');
  assert.match(res.headers['content-security-policy'], /script-src 'self'/);
  assert.equal(res.headers['x-frame-options'], 'DENY');
  assert.ok(res.headers['permissions-policy']);
});

test('an invalid customer id is rejected', async () => {
  await (await client(app, 'karim')).get('/advisor').query({ customer: '<script>' }).expect(400);
});

test('a POST without a CSRF token is refused', async () => {
  const sana = await client(app, 'sana');
  await sana.post('/workforce/simulate').type('form').send({ queue: 'B' }).expect(403);
});

test('an invalid simulation shows errors instead of calling the agent', async () => {
  const res = await post(await client(app, 'sana'), '/workforce/simulate', '/workforce',
    { queue: 'B', extraAdvisors: '50', from: '16:00', to: '14:00' });
  assert.equal(res.status, 200);
  assert.match(res.text, /At most 10/);
  assert.match(res.text, /End time must be after start time/);
  assert.doesNotMatch(res.text, /Ranked recommendations/);
});

test('a valid simulation returns a result', async () => {
  const res = await post(await client(app, 'sana'), '/workforce/simulate', '/workforce',
    { queue: 'B', extraAdvisors: '2', from: '14:00', to: '16:00' });
  assert.equal(res.status, 200);
  assert.match(res.text, /Ranked recommendations/);
  assert.match(res.text, /130 s/); // 240 - 2 x 55
});

test('a wrong password is refused and five failures lock the account', async () => {
  const anon = request.agent(app.getHttpServer());
  for (let i = 0; i < 5; i++) {
    const page = await anon.get('/login');
    const res = await anon.post('/login').type('form').send({ username: 'leila', password: 'wrong-password', _csrf: csrfOf(page.text) });
    assert.equal(res.headers.location, '/login?error');
  }
  const page = await anon.get('/login');
  const locked = await anon.post('/login').type('form').send({ username: 'leila', password: PASSWORD, _csrf: csrfOf(page.text) });
  assert.equal(locked.headers.location, '/login?error'); // right password, still locked
});

test('signing out ends the session', async () => {
  const nour = await client(app, 'nour');
  await nour.get('/quality').expect(200);
  const res = await post(nour, '/logout', '/quality', {});
  assert.equal(res.headers.location, '/login?logout');
  await nour.get('/quality').expect(302);
});
