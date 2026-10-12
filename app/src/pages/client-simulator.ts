import { customerLine } from './customer-llm';

/**
 * Client Simulator agent (deck: persona engine, emotional dynamics, memory, outcome signals).
 * Deterministic and stateless: a call is replayed from the moves chosen so far, so the same URL
 * always shows the same call. Swap for the Python agent behind AgentGateway when it exists.
 */
export const MAX_MOVES = 6;

/** Traits are 0..1 sensitivities; mood and patience start values are 0..100. */
export const PERSONAS = {
  IMPATIENT: { label: 'Impatient but fair', blurb: 'Loyal if treated well, hates waiting.', mood: 55, patience: 65, repeat: 0.9, empathy: 0.5, speed: 0.9 },
  ANXIOUS: { label: 'Anxious first-timer', blurb: 'Needs reassurance and plain words.', mood: 50, patience: 75, repeat: 0.5, empathy: 0.95, speed: 0.4 },
  ANGRY_PREMIUM: { label: 'Angry premium client', blurb: 'High expectations, short fuse.', mood: 35, patience: 45, repeat: 1.0, empathy: 0.6, speed: 1.0 },
  LOYAL_AT_RISK: { label: 'Loyal but at risk', blurb: 'Six years with us, one bad call from leaving.', mood: 60, patience: 60, repeat: 0.8, empathy: 0.8, speed: 0.6 },
  NEW_SUBSCRIBER: { label: 'New subscriber', blurb: 'Patient, but needs everything explained.', mood: 65, patience: 85, repeat: 0.3, empathy: 0.7, speed: 0.3 },
} as const;
export type PersonaKey = keyof typeof PERSONAS;

export const DIFFICULTIES = {
  EASY: { label: 'Easy', penalty: 0.7, patienceShift: 15 },
  MEDIUM: { label: 'Medium', penalty: 1.0, patienceShift: 0 },
  HARD: { label: 'Hard', penalty: 1.4, patienceShift: -15 },
} as const;
export type DifficultyKey = keyof typeof DIFFICULTIES;

export const INTENTS = {
  BILLING: { label: 'Billing', opening: 'I was charged twice on my September bill.' },
  ROAMING: { label: 'Roaming', opening: 'My roaming bundle did not work abroad.' },
  CANCELLATION: { label: 'Cancellation', opening: 'I want to cancel, and this fee makes no sense.' },
} as const;
export type IntentKey = keyof typeof INTENTS;

export const MOVES = {
  EMPATHY: { label: 'Acknowledge the frustration and use her history' },
  ASK_REPEAT: { label: 'Ask her to explain the problem again' },
  TRANSFER: { label: 'Transfer her to the billing team' },
  CHECK_POLICY: { label: 'Check the refund policy before promising' },
  PROMISE: { label: 'Promise the refund right away' },
  FOLLOW_UP: { label: 'Confirm the fix in writing and set a follow-up' },
  OTHER: { label: 'Said something else' }, // only reached by typed replies that match no move; has no button
} as const;
export type MoveKey = keyof typeof MOVES;

/** `said` is what the advisor typed, or null when a button was used. */
export interface Turn { move: MoveKey; said: string | null; client: string; mood: number; patience: number }
export interface Outcome { verdict: string; expectationMet: boolean; churnRisk: number; effort: number; notes: string[] }
export interface Session {
  persona: PersonaKey; mix: PersonaKey | null; difficulty: DifficultyKey; intent: IntentKey; memory: boolean;
  opening: string; turns: Turn[]; mood: number; patience: number; outcome: Outcome | null;
}

const clamp = (v: number) => Math.max(0, Math.min(100, Math.round(v)));

export function replay(persona: PersonaKey, mix: PersonaKey | null, difficulty: DifficultyKey, intent: IntentKey,
                       memory: boolean, moves: MoveKey[], said: (string | null)[] = []): Session {
  const p = PERSONAS[persona], d = DIFFICULTIES[difficulty];
  let repeat: number = p.repeat, empathy: number = p.empathy, speed: number = p.speed, mood: number = p.mood, patience: number = p.patience;
  if (mix) { // persona mixing: blend the two profiles
    const q = PERSONAS[mix];
    repeat = (repeat + q.repeat) / 2; empathy = (empathy + q.empathy) / 2; speed = (speed + q.speed) / 2;
    mood = Math.trunc((mood + q.mood) / 2); patience = Math.trunc((patience + q.patience) / 2);
  }
  mood = clamp(mood);
  patience = clamp(patience + d.patienceShift);

  const opening = INTENTS[intent].opening + (memory ? ' This is the third time I call about it.' : '');
  const turns: Turn[] = [];
  let effort = 0, checked = false, risky = false, closed = false, hungUp = false;
  const neg = d.penalty;

  for (const [i, m] of moves.entries()) {
    if (turns.length >= MAX_MOVES || closed || hungUp) break;
    let dm: number, dp: number;
    switch (m) {
      case 'EMPATHY': dm = memory ? 10 + 14 * empathy : 4 + 8 * empathy; dp = 4; break;
      case 'ASK_REPEAT': dm = -(8 + 10 * repeat) * neg * (memory ? 1.3 : 1); dp = -(10 + 12 * repeat) * neg; effort++; break;
      case 'TRANSFER': dm = -8 * neg; dp = -(8 + 10 * speed) * neg; effort++; break;
      case 'CHECK_POLICY': dm = 2; dp = -(4 + 6 * speed) * neg; checked = true; break;
      case 'PROMISE': dm = 14; dp = 5; if (!checked) risky = true; break;
      case 'OTHER': dm = 1; dp = -3; break; // small talk: time passes, nothing is solved
      default: dm = 8 + 6 * empathy; dp = 6; closed = true;
    }
    mood = clamp(mood + dm);
    patience = clamp(patience + dp);
    if (patience <= 0) hungUp = true;
    const advisorSaid = said[i] ?? null;
    turns.push({ move: m, said: advisorSaid, client: customerLine({ persona, intent, difficulty, move: m, mood, memory, hungUp, turn: i, advisorSaid }), mood, patience });
  }

  let outcome: Outcome | null = null;
  if (hungUp || closed || turns.length >= MAX_MOVES) {
    const met = closed && !risky && !hungUp && mood >= 55;
    const churnRisk = clamp(100 - mood * 0.55 - patience * 0.35 + effort * 7 + (risky ? 12 : 0) + (hungUp ? 25 : 0));
    const notes: string[] = [];
    if (effort > 0) notes.push(`Customer effort: the client had to repeat or be transferred ${effort} time(s).`);
    if (risky) notes.push('Compliance risk: a refund was promised before the policy was checked.');
    if (memory && moves.includes('ASK_REPEAT')) notes.push('Memory ignored: the history was on file but the client was asked to repeat.');
    if (!closed && !hungUp) notes.push('The call ended without a written follow-up.');
    const verdict = hungUp ? 'The client hung up.'
      : met ? 'Resolved: the client leaves satisfied.'
      : closed ? 'Closed, but trust is shaky.' : 'Call left open.';
    outcome = { verdict, expectationMet: met, churnRisk, effort, notes };
  }
  return { persona, mix, difficulty, intent, memory, opening, turns, mood, patience, outcome };
}
