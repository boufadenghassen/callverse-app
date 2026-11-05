import { after, before, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { NestExpressApplication } from '@nestjs/platform-express';
import { client, count, csrfOf, startApp } from './helpers';
import { customerLine, readAdvisor } from '../src/pages/customer-llm';
import { MoveKey, PersonaKey, PERSONAS, replay } from '../src/pages/client-simulator';

describe('reading the advisor', () => {
  const cases: [string, MoveKey][] = [
    ["I'm so sorry about that, I understand how frustrating this is.", 'EMPATHY'],
    ['Could you repeat the problem from the start, please?', 'ASK_REPEAT'],
    ["I'll transfer you to the billing team.", 'TRANSFER'],
    ['Let me check the refund policy first.', 'CHECK_POLICY'],
    ['I promise you will get a refund right away.', 'PROMISE'],
    ["I'll send you a confirmation by email and call you back tomorrow.", 'FOLLOW_UP'],
    ['The weather is nice today.', 'OTHER'],
    ['', 'OTHER'],
  ];
  for (const [text, move] of cases) test(`"${text}" is read as ${move}`, () => assert.equal(readAdvisor(text), move));

  test('checking the policy before promising is not mistaken for a promise', () => {
    assert.equal(readAdvisor('I need to check the policy before promising any refund.'), 'CHECK_POLICY');
  });
  test('an apology with a real action counts as the action', () => {
    assert.equal(readAdvisor("I'm sorry, could you explain it again?"), 'ASK_REPEAT');
  });
});

describe('the customer talks', () => {
  const ctx = { persona: 'ANXIOUS' as PersonaKey, intent: 'BILLING' as const, difficulty: 'MEDIUM' as const, move: 'EMPATHY' as MoveKey,
    mood: 50, memory: false, hungUp: false, turn: 0, advisorSaid: null };

  test('the same situation always gives the same line', () => assert.equal(customerLine(ctx), customerLine({ ...ctx })));

  test('different situations give different lines (not three canned replies)', () => {
    const lines = new Set<string>();
    for (const persona of Object.keys(PERSONAS) as PersonaKey[]) for (const turn of [0, 1, 2, 3]) for (const said of [null, 'a', 'b'])
      lines.add(customerLine({ ...ctx, persona, turn, advisorSaid: said }));
    assert.ok(lines.size >= 20, `only ${lines.size} distinct lines`);
  });

  test('a hung-up customer says goodbye', () => assert.match(customerLine({ ...ctx, hungUp: true }), /goodbye|hanging up|enough/i));

  test('typed replies drive the same rules as the buttons', () => {
    const typed = replay('IMPATIENT', null, 'MEDIUM', 'BILLING', true,
      ['EMPATHY', 'CHECK_POLICY', 'FOLLOW_UP'], ['I understand, sorry.', 'Let me check the policy.', 'I will email you a confirmation.']);
    const buttons = replay('IMPATIENT', null, 'MEDIUM', 'BILLING', true, ['EMPATHY', 'CHECK_POLICY', 'FOLLOW_UP']);
    assert.equal(typed.outcome?.verdict, buttons.outcome?.verdict);
    assert.equal(typed.mood, buttons.mood);
    assert.equal(typed.turns[0].said, 'I understand, sorry.');
  });

  test('she hears a raised voice, rude words and shouting', () => {
    const angry = { emotion: 'anger', mood: 14 };
    assert.equal(readAdvisor('I am sorry about that.', angry), 'RUDE');                                   // polite words, angry voice
    assert.equal(readAdvisor('I am sorry about that.', { emotion: 'happy', mood: 85 }), 'EMPATHY');
    assert.equal(readAdvisor('I am sorry about that.', { emotion: 'anger', mood: 60 }), 'EMPATHY');       // a weak reading is not enough
    assert.equal(readAdvisor('I am sorry about that.', { emotion: 'sad', mood: 5 }), 'EMPATHY');          // only anger or disgust counts
    for (const rude of ["Don't be stupid.", 'shut up and listen', 'I WANT MY MONEY BACK NOW', 'What are you doing!!!']) assert.equal(readAdvisor(rude), 'RUDE', rude);
    assert.equal(readAdvisor('Please send the SMS and USB details.'), 'OTHER');                          // acronyms are not shouting
  });

  test('a raised voice costs patience, spoils the ending and is noted', () => {
    const calm = replay('IMPATIENT', null, 'MEDIUM', 'BILLING', false, ['EMPATHY'], ['I am sorry.']);
    const rude = replay('IMPATIENT', null, 'MEDIUM', 'BILLING', false, ['RUDE'], ['I am sorry.']);
    assert.ok(rude.mood < calm.mood - 15 && rude.patience < calm.patience - 15);
    const done = replay('IMPATIENT', null, 'MEDIUM', 'BILLING', false, ['RUDE', 'EMPATHY', 'CHECK_POLICY', 'FOLLOW_UP']);
    assert.equal(done.outcome?.expectationMet, false);
    assert.ok(done.outcome?.notes.some((n) => /Conduct/.test(n)));
    assert.equal(replay('IMPATIENT', null, 'MEDIUM', 'BILLING', false, ['RUDE', 'RUDE', 'RUDE']).outcome?.verdict, 'The client hung up.');
  });

  test('she answers what was actually said when it matches no move', () => {
    const line = (said: string | null, mood = 50) => customerLine({ persona: 'NEW_SUBSCRIBER', intent: 'BILLING', difficulty: 'MEDIUM', move: 'OTHER', mood, memory: false, hungUp: false, turn: 0, advisorSaid: said });
    assert.match(line('Why did you put $2,000?'), /\$2,000/);
    assert.match(line('Is this about 45 TND?'), /45 TND/);
    assert.match(line('Hello, how are you today?'), /my bill/);
    assert.match(line('Can you give me your name?'), /my bill/);
    assert.doesNotMatch(line('The weather is nice today.'), /my bill/);
    assert.doesNotMatch(line(null), /my bill/);
    assert.equal(line('Why did you put $2,000?'), line('Why did you put $2,000?'));
    assert.notEqual(line('Why did you put $2,000?', 10), line('Why did you put $2,000?', 90));
  });

  test('small talk wastes patience and solves nothing', () => {
    const s = replay('IMPATIENT', null, 'MEDIUM', 'BILLING', false, ['OTHER', 'OTHER']);
    assert.ok(s.patience < 65);
    assert.equal(s.outcome, null);
  });
});

describe('typing a reply in the page', () => {
  let app: NestExpressApplication;
  before(async () => { app = await startApp(); });
  after(async () => { await app.close(); });

  async function say(reply: string, query: Record<string, string> = {}) {
    const yasmine = await client(app, 'yasmine');
    const qs = new URLSearchParams({ persona: 'IMPATIENT', ...query }).toString();
    const page = await yasmine.get(`/client?${qs}`);
    const field = (name: string) => new RegExp(`name="${name}" value="([^"]*)"`).exec(page.text)?.[1] ?? '';
    const body = { _csrf: csrfOf(page.text), persona: 'IMPATIENT', mix: '', difficulty: 'MEDIUM', intent: 'BILLING', memory: 'false',
      moves: field('moves'), said: field('said').replace(/&quot;/g, '"'), reply };
    return { yasmine, res: await yasmine.post('/client/say').type('form').send(body) };
  }

  test('a typed reply is read, added to the call and shown with how it was read', async () => {
    const { yasmine, res } = await say("I'm sorry about that, let me check the refund policy first.");
    assert.equal(res.status, 302);
    assert.match(res.headers.location, /moves=CHECK_POLICY/);
    const html = (await yasmine.get(res.headers.location)).text;
    assert.match(html, /let me check the refund policy first/);
    assert.match(html, /read as: check the refund policy before promising/);
  });

  test('buttons and typing mix in the same call', async () => {
    const { yasmine, res } = await say('I promise you a refund right away.');
    const html = (await yasmine.get(res.headers.location)).text;
    const button = /href="([^"]*moves=PROMISE%2CEMPATHY[^"]*)"/.exec(html.replace(/&amp;/g, '&'));
    assert.ok(button, 'the next button link keeps the typed turn and adds the new move');
    assert.match(decodeURIComponent(button![1].replaceAll('+', ' ')), /said=\["I promise you a refund right away\.",null\]/);
  });

  test('an empty reply changes nothing, and a missing CSRF token is refused', async () => {
    const { res } = await say('   ');
    assert.equal(res.status, 302);
    assert.doesNotMatch(res.headers.location, /moves=/);
    const yasmine = await client(app, 'yasmine');
    await yasmine.post('/client/say').type('form').send({ reply: 'hello' }).expect(403);
  });

  test('other roles cannot use it, and tampered state is rejected', async () => {
    const karim = await client(app, 'karim');
    const page = await karim.get('/advisor');
    await karim.post('/client/say').type('form').send({ _csrf: csrfOf(page.text), reply: 'hi' }).expect(403);
    await (await client(app, 'yasmine')).get('/client').query({ said: '{"not":"an array"}' }).expect(400);
    await (await client(app, 'yasmine')).get('/client').query({ said: JSON.stringify(['x'.repeat(500)]) }).expect(400);
  });

  test('the page offers the typed-reply box and still has the six buttons', async () => {
    const html = (await (await client(app, 'yasmine')).get('/client')).text;
    assert.match(html, /id="reply"/);
    assert.equal(count(html, 'class="choice"'), 6);
  });
});
