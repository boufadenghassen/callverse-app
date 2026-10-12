import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { NestExpressApplication } from '@nestjs/platform-express';
import { client, startApp } from './helpers';

let app: NestExpressApplication;
before(async () => { app = await startApp(); });
after(async () => { await app.close(); });

test('a missing page shows a friendly 404 with a way home', async () => {
  const res = await (await client(app, 'karim')).get('/no-such-page').expect(404);
  assert.match(res.text, /find that page/);
  assert.match(res.text, /Back to orqestra/);
  assert.doesNotMatch(res.text, /Sign in<\/a>/, 'a signed-in user is not asked to sign in');
});

test('a page for another role explains itself instead of a bare 403', async () => {
  const res = await (await client(app, 'karim')).get('/workforce').expect(403);
  assert.match(res.text, /another role/);
});

test('a bad request says what to do', async () => {
  const res = await (await client(app, 'karim')).get('/advisor').query({ customer: '<script>' }).expect(400);
  assert.match(res.text, /didn(&#39;|')t look right/);
});

test('every workspace page opens with its role tag', async () => {
  const pages: [string, string, RegExp][] = [['karim', '/advisor', /Customer advisor agent/], ['sana', '/workforce', /Workforce manager agent/],
    ['nour', '/quality', /Quality analyst agent/], ['yasmine', '/client', /Client simulator agent/], ['admin', '/insights', /Presentation/], ['admin', '/', /Welcome/]];
  for (const [user, path, tag] of pages) {
    const html = (await (await client(app, user)).get(path).expect(200)).text;
    assert.match(html, /class="eyebrow"/, `${path} has an eyebrow`);
    assert.match(html, tag, `${path} names its role`);
  }
});
