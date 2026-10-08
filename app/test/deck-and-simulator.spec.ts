import { after, before, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { NestExpressApplication } from '@nestjs/platform-express';
import { client, count, startApp } from './helpers';
import { DifficultyKey, MoveKey, PersonaKey, replay } from '../src/pages/client-simulator';
import { PERSONAS as DECK } from '../src/pages/deck-content';

const run = (p: PersonaKey, d: DifficultyKey, memory: boolean, ...moves: MoveKey[]) => replay(p, null, d, 'BILLING', memory, moves);

describe('client simulator', () => {
  test('empathy, then policy, then follow-up resolves the call', () => {
    const s = run('IMPATIENT', 'MEDIUM', true, 'EMPATHY', 'CHECK_POLICY', 'FOLLOW_UP');
    assert.equal(s.outcome?.expectationMet, true);
    assert.ok(s.outcome!.churnRisk < 40);
  });

  test('asking an angry client to repeat on hard makes them hang up', () => {
    const s = run('ANGRY_PREMIUM', 'HARD', true, 'ASK_REPEAT');
    assert.match(s.outcome!.verdict, /hung up/);
    assert.equal(s.outcome!.churnRisk, 100);
    assert.ok(s.outcome!.notes.some((n) => n.includes('Memory ignored')));
  });

  test('promising before checking policy is flagged and never counts as met', () => {
    const s = run('IMPATIENT', 'MEDIUM', false, 'PROMISE', 'FOLLOW_UP');
    assert.equal(s.outcome!.expectationMet, false);
    assert.ok(s.outcome!.notes.some((n) => n.includes('Compliance risk')));
  });

  test('the same moves always give the same call', () => {
    assert.deepEqual(run('ANXIOUS', 'MEDIUM', false, 'EMPATHY', 'TRANSFER'), run('ANXIOUS', 'MEDIUM', false, 'EMPATHY', 'TRANSFER'));
  });

  test('every idea has a decision and a coverage', () => {
    const ideas = DECK.flatMap((p) => p.ideas);
    assert.equal(DECK.length, 7);
    assert.equal(ideas.length, 28);
    assert.ok(ideas.every((i) => ['PRODUCTION', 'PROTOTYPE', 'PERSPECTIVE'].includes(i.decision)));
    assert.ok(ideas.every((i) => ['LIVE', 'PARTIAL', 'ROADMAP'].includes(i.coverage)));
  });
});

describe('pages', () => {
  let app: NestExpressApplication;
  before(async () => { app = await startApp(); });
  after(async () => { await app.close(); });

  test('the client role opens the simulator and plays a move', async () => {
    const yasmine = await client(app, 'yasmine');
    assert.match((await yasmine.get('/client')).text, /Live call/);
    await yasmine.get('/client').query({ moves: 'EMPATHY' }).expect(200);
  });

  test('invalid moves are rejected', async () => {
    await (await client(app, 'yasmine')).get('/client').query({ moves: 'NOT_A_MOVE' }).expect(400);
  });

  test('an advisor cannot open the simulator but sees the presentation pages', async () => {
    const karim = await client(app, 'karim');
    await karim.get('/client').expect(403);
    for (const page of ['/personas', '/ideas', '/pipeline']) await karim.get(page).expect(200);
  });

  test('the complaints page shows lanes and the early warning', async () => {
    const html = (await (await client(app, 'amine')).get('/complaints')).text;
    assert.match(html, /Early warning/);
    assert.match(html, /lane-critical/);
  });

  test('presentation mode and the feasibility map render', async () => {
    const karim = await client(app, 'karim');
    const present = (await karim.get('/present')).text;
    assert.match(present, /Questions\?/);
    assert.match(present, /Live demo/);
    assert.equal(count((await karim.get('/ideas')).text, 'class="mdot '), 28);
  });

  test('the quality page has a timeline pin per criterion', async () => {
    assert.equal(count((await (await client(app, 'nour')).get('/quality')).text, 'role="button"'), 8); // 2 reviews x 4 criteria
  });

  test('the workforce page has the scrubber and heat strip', async () => {
    const html = (await (await client(app, 'sana')).get('/workforce')).text;
    assert.match(html, /id="hour"/);
    assert.match(html, /class="heat"/);
  });

  test('home shows a live number per workspace', async () => {
    const html = (await (await client(app, 'admin')).get('/')).text;
    assert.match(html, /need a supervisor/);
    assert.match(html, /Presentation mode/);
  });

  test('only the admin sees the demo tour button', async () => {
    assert.match((await (await client(app, 'admin')).get('/')).text, /data-tour="start"/);
    assert.doesNotMatch((await (await client(app, 'karim')).get('/')).text, /data-tour="start"/);
  });

  test('slides carry speaker notes and every page has a skip link', async () => {
    const karim = await client(app, 'karim');
    assert.equal(count((await karim.get('/present')).text, 'data-notes='), 14); // 7 fixed slides + 7 personas
    const advisor = (await karim.get('/advisor')).text;
    assert.match(advisor, /Skip to content/);
    assert.match(advisor, /id="main"/);
  });

  test('complaint cards are draggable and escalatable', async () => {
    const html = (await (await client(app, 'amine')).get('/complaints')).text;
    assert.equal(count(html, 'draggable="true"'), 3);
    assert.equal(count(html, 'data-escalate'), 3);
  });

  test('a finished call exposes its outcome for the history', async () => {
    const html = (await (await client(app, 'yasmine')).get('/client').query({ moves: 'EMPATHY,CHECK_POLICY,FOLLOW_UP' })).text;
    assert.match(html, /data-verdict=/);
    assert.match(html, /id="history"/);
  });
});
