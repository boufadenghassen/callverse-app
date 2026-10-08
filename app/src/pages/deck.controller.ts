import { BadRequestException, Controller, Get, Query, Render, Req } from '@nestjs/common';
import type { Request } from 'express';
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

  @Roles('CLIENT') @Get('client') @Render('client')
  client(@Query() q: Record<string, unknown>) {
    const persona = enumParam<PersonaKey>(q.persona, PERSONAS, 'IMPATIENT')!;
    const mixParam = enumParam<PersonaKey>(q.mix, PERSONAS, null);
    const mix = mixParam === persona ? null : mixParam;
    const difficulty = enumParam<DifficultyKey>(q.difficulty, DIFFICULTIES, 'MEDIUM')!;
    const intent = enumParam<IntentKey>(q.intent, INTENTS, 'BILLING')!;
    const memory = q.memory === 'true';

    const movesParam = q.moves === undefined ? '' : q.moves;
    if (typeof movesParam !== 'string' || movesParam.length > 120) throw new BadRequestException();
    const moves = movesParam === '' ? [] : movesParam.split(',').map((m) => enumParam<MoveKey>(m, MOVES, null)!);

    const s = replay(persona, mix, difficulty, intent, memory, moves);
    const start = replay(persona, mix, difficulty, intent, memory, []).mood;
    const moods = [start, ...s.turns.map((t) => t.mood)];
    const moodPoints = moods.map((m, i) => ({ x: 20 + i * 43, y: 70 - Math.round(m * 0.6) }));

    const href = (extra: Record<string, string> = {}) => {
      const p = new URLSearchParams({ persona, ...(mix ? { mix } : {}), difficulty, intent, memory: String(memory), ...extra });
      return `/client?${p}`;
    };
    const played = s.turns.map((t) => t.move).join(',');
    return {
      s: {
        ...s, persona: { key: persona, ...PERSONAS[persona] }, mix: mix, difficulty: { key: difficulty, ...DIFFICULTIES[difficulty] },
        intent, ended: s.outcome !== null,
        turns: s.turns.map((t) => ({ ...t, label: MOVES[t.move].label })),
      },
      moodPoints, moodCurve: moodPoints.map((p) => `${p.x},${p.y}`).join(' '),
      personas: Object.entries(PERSONAS).map(([key, v]) => ({ key, label: v.label })),
      difficulties: Object.entries(DIFFICULTIES).map(([key, v]) => ({ key, label: v.label })),
      intents: Object.entries(INTENTS).map(([key, v]) => ({ key, label: v.label })),
      choices: Object.entries(MOVES).map(([key, v]) => ({ label: v.label, href: href({ moves: played ? `${played},${key}` : key }) })),
      replayHref: href(),
      outcomeKey: [persona, String(mix), difficulty, intent, memory, played].join('|'),
      maxMoves: MAX_MOVES,
    };
  }
}
