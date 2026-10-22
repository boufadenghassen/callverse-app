import { BadRequestException, Body, Controller, Get, HttpCode, Post, Query, Render, Req, Res } from '@nestjs/common';
import type { Request, Response } from 'express';
import { readAdvisor } from './customer-llm';
import { Roles } from '../auth/access.guard';
import { buildInsights, DIMENSIONS, FAIRNESS, METRICS, MetricKey, MIN_GROUP } from './insights';
import { BEFORE_AFTER, EMPATHY, JOURNEY, PERSONAS as DECK } from './deck-content';
import {
  DIFFICULTIES, DifficultyKey, INTENTS, IntentKey, MAX_MOVES, MOVES, MoveKey, PERSONAS, PersonaKey, replay,
} from './client-simulator';

const ideas = DECK.flatMap((p) => p.ideas);
const count = (key: 'decision' | 'coverage', value: string) => ideas.filter((i) => i[key] === value).length;
const decisions = () => ({
  total: ideas.length, production: count('decision', 'PRODUCTION'), prototype: count('decision', 'PROTOTYPE'), perspective: count('decision', 'PERSPECTIVE'),
});

/** Which workspaces the signed-in user may open, keyed by persona key. */
const canOpen = (req: Request) =>
  Object.fromEntries(DECK.map((p) => [p.key, req.session.user?.role === 'ADMIN' || req.session.user?.role === p.needsRole]));

/** Emotion curve for the client journey as SVG points (viewBox 600 x 160). */
const journeyCurve = () => JOURNEY.map((s, i) => `${50 + i * 100},${140 - s.level * 30}`).join(' ');

/** One dot per idea on the tech (x) by impact (y) grid; dots in the same cell fan out in rows. */
function matrix() {
  const level = (v: string) => (v === 'High' ? 2 : v === 'Medium' ? 1 : 0);
  const used = new Array(9).fill(0);
  return DECK.flatMap((p) => p.ideas.map((i) => {
    const t = level(i.tech), m = level(i.impact), k = used[t * 3 + m]++;
    return {
      x: 70 + t * 110 + 14 + (k % 5) * 20, y: 270 - m * 85 - 14 - Math.floor(k / 5) * 20,
      text: `${p.name}: ${i.group} (${i.decision.toLowerCase()})`, decision: i.decision.toLowerCase(),
    };
  }));
}

function enumParam<T extends string>(value: unknown, allowed: Record<T, unknown>, fallback: T | null): T | null {
  if (value === undefined || value === '') return fallback;
  if (typeof value === 'string' && Object.hasOwn(allowed, value)) return value as T;
  throw new BadRequestException();
}

/** Presentation pages (personas, ideas, pipeline) and the Client Simulator workspace. */
@Controller()
export class DeckController {
  @Get('personas') @Render('personas')
  personas(@Req() req: Request) {
    return { personas: DECK, canOpen: canOpen(req), journey: JOURNEY, journeyCurve: journeyCurve(), empathy: EMPATHY };
  }

  @Get('ideas') @Render('ideas')
  ideasPage(@Req() req: Request) {
    return {
      personas: DECK, canOpen: canOpen(req), ...decisions(), live: count('coverage', 'LIVE'), partial: count('coverage', 'PARTIAL'),
      roadmap: count('coverage', 'ROADMAP'), matrix: matrix(),
    };
  }

  /** Full-screen walkthrough built from the same deck data, with live-demo buttons. */
  @Get('present') @Render('present')
  present(@Req() req: Request) {
    return { personas: DECK, canOpen: canOpen(req), journey: JOURNEY, journeyCurve: journeyCurve(), beforeAfter: BEFORE_AFTER, ...decisions() };
  }

  @Get('pipeline') @Render('pipeline')
  pipeline() {
    return { beforeAfter: BEFORE_AFTER };
  }

  /** Customer statistics by age, sex and region (demo data). Presentation extra: see insights.ts for how to remove it. */
  @Get('insights') @Render('insights')
  insights(@Query() q: Record<string, unknown>) {
    const pick = (v: unknown, allowed: readonly string[]) => {
      if (v === undefined || v === '') return '';
      if (typeof v === 'string' && allowed.includes(v)) return v;
      throw new BadRequestException();
    };
    const f = {
      age: pick(q.age, DIMENSIONS.age.values), sex: pick(q.sex, DIMENSIONS.sex.values), region: pick(q.region, DIMENSIONS.region.values),
      metric: (pick(q.metric, Object.keys(METRICS)) || 'churn') as MetricKey,
    };
    return {
      f, dimensions: DIMENSIONS, metrics: Object.entries(METRICS).map(([key, m]) => ({ key, label: m.label })),
      minGroup: MIN_GROUP, fairness: FAIRNESS, ...buildInsights(f),
    };
  }

  // ---- Yasmine: client simulator -------------------------------------------------------------

  @Roles('CLIENT', 'TRAINER') @Get('client') @Render('client')
  client(@Query() q: Record<string, unknown>) {
    const call = parseCall(q);
    const s = replay(call.persona, call.mix, call.difficulty, call.intent, call.memory, call.moves, call.said);
    const start = replay(call.persona, call.mix, call.difficulty, call.intent, call.memory, []).mood;
    const moods = [start, ...s.turns.map((t) => t.mood)];
    const moodPoints = moods.map((m, i) => ({ x: 20 + i * 43, y: 70 - Math.round(m * 0.6) }));

    // only the turns that really happened (the call may have ended before all the moves in the URL)
    const played = s.turns.map((t) => t.move), playedSaid = s.turns.map((t) => t.said);
    const next = (move: MoveKey) => callUrl(call, [...played, move], [...playedSaid, null]);
    return {
      s: {
        ...s, persona: { key: call.persona, ...PERSONAS[call.persona] }, mix: call.mix, difficulty: { key: call.difficulty, ...DIFFICULTIES[call.difficulty] },
        intent: call.intent, ended: s.outcome !== null,
        turns: s.turns.map((t) => ({ ...t, label: MOVES[t.move].label })),
      },
      moodPoints, moodCurve: moodPoints.map((p) => `${p.x},${p.y}`).join(' '),
      personas: Object.entries(PERSONAS).map(([key, v]) => ({ key, label: v.label })),
      difficulties: Object.entries(DIFFICULTIES).map(([key, v]) => ({ key, label: v.label })),
      intents: Object.entries(INTENTS).map(([key, v]) => ({ key, label: v.label })),
      choices: (Object.keys(MOVES) as MoveKey[]).filter((k) => k !== 'OTHER' && k !== 'RUDE').map((k) => ({ label: MOVES[k].label, href: next(k) })),
      // the typed-reply form carries the whole call along as hidden fields
      state: {
        persona: call.persona, mix: call.mix ?? '', difficulty: call.difficulty, intent: call.intent, memory: String(call.memory),
        moves: played.join(','), said: playedSaid.some((x) => x !== null) ? JSON.stringify(playedSaid) : '',
      },
      replayHref: callUrl(call, [], []),
      outcomeKey: [call.persona, String(call.mix), call.difficulty, call.intent, call.memory, played.join(',')].join('|'),
      maxMoves: MAX_MOVES,
    };
  }

  /** The advisor typed a reply: read it as a move, add it to the call and show the new state (redirect keeps the URL replayable). */
  @Roles('CLIENT') @Post('client/say') @HttpCode(302)
  say(@Body() body: Record<string, unknown>, @Res() res: Response) {
    const call = parseCall(body);
    const text = typeof body.reply === 'string' ? body.reply.replace(/\p{Cc}/gu, ' ').trim().slice(0, MAX_SAID) : '';
    const s = replay(call.persona, call.mix, call.difficulty, call.intent, call.memory, call.moves, call.said);
    if (!text || s.outcome) return res.redirect(callUrl(call, s.turns.map((t) => t.move), s.turns.map((t) => t.said)));
    return res.redirect(callUrl(call, [...s.turns.map((t) => t.move), readAdvisor(text)], [...s.turns.map((t) => t.said), text]));
  }
}

const MAX_SAID = 200;

interface Call { persona: PersonaKey; mix: PersonaKey | null; difficulty: DifficultyKey; intent: IntentKey; memory: boolean; moves: MoveKey[]; said: (string | null)[] }

/** Reads and validates a call from a query string or a form body. Anything unexpected is a 400. */
function parseCall(q: Record<string, unknown>): Call {
  const persona = enumParam<PersonaKey>(q.persona, PERSONAS, 'IMPATIENT')!;
  const mixParam = enumParam<PersonaKey>(q.mix, PERSONAS, null);
  const movesParam = q.moves === undefined ? '' : q.moves;
  if (typeof movesParam !== 'string' || movesParam.length > 120) throw new BadRequestException();
  const moves = movesParam === '' ? [] : movesParam.split(',').map((m) => enumParam<MoveKey>(m, MOVES, null)!);

  let said: (string | null)[] = [];
  if (q.said !== undefined && q.said !== '') {
    try {
      if (typeof q.said !== 'string' || q.said.length > 1800) throw new Error();
      const parsed: unknown = JSON.parse(q.said);
      if (!Array.isArray(parsed) || parsed.length > MAX_MOVES || !parsed.every((x) => x === null || (typeof x === 'string' && x.length <= MAX_SAID))) throw new Error();
      said = parsed as (string | null)[];
    } catch { throw new BadRequestException(); }
  }
  return {
    persona, mix: mixParam === persona ? null : mixParam,
    difficulty: enumParam<DifficultyKey>(q.difficulty, DIFFICULTIES, 'MEDIUM')!, intent: enumParam<IntentKey>(q.intent, INTENTS, 'BILLING')!,
    memory: q.memory === 'true', moves, said,
  };
}

function callUrl(c: Call, moves: MoveKey[], said: (string | null)[]): string {
  const p = new URLSearchParams({ persona: c.persona, ...(c.mix ? { mix: c.mix } : {}), difficulty: c.difficulty, intent: c.intent, memory: String(c.memory) });
  if (moves.length) p.set('moves', moves.join(','));
  const aligned = moves.map((_, i) => said[i] ?? null);
  if (aligned.some((x) => x !== null)) p.set('said', JSON.stringify(aligned));
  return `/client?${p}`;
}
