import type { ScenarioDetail } from '../agents/models';
import type { DifficultyKey, IntentKey, PersonaKey } from './client-simulator';

/** What a training scenario becomes in the customer simulator, with the reasons, so the trainer sees how the scenario was read. */
export interface SimSettings { persona: PersonaKey; mix: PersonaKey | null; difficulty: DifficultyKey; intent: IntentKey; memory: boolean; why: string[] }

const LABEL: Record<PersonaKey, string> = {
  IMPATIENT: 'Impatient but fair', ANXIOUS: 'Anxious first-timer', ANGRY_PREMIUM: 'Angry premium client', LOYAL_AT_RISK: 'Loyal but at risk', NEW_SUBSCRIBER: 'New subscriber',
};
const BY_SEGMENT: Record<string, PersonaKey> = { new: 'NEW_SUBSCRIBER', loyal: 'LOYAL_AT_RISK', dissatisfied: 'IMPATIENT', premium: 'ANGRY_PREMIUM', at_risk: 'LOYAL_AT_RISK' };
/** The scenario catalogue has 15 problems; our simulator has three reasons for a call, so each problem goes to the closest one. */
const BY_INTENT: Record<string, IntentKey> = {
  double_billing: 'BILLING', refund_status: 'BILLING', fee_dispute: 'BILLING', unrecognized_charge: 'BILLING', refund_received: 'BILLING', plan_change: 'BILLING',
  contract_renewal_offer: 'BILLING', data_allowance_question: 'BILLING', lost_sim_or_phone: 'BILLING',
  roaming_bill_shock: 'ROAMING', line_cut: 'ROAMING', slow_internet: 'ROAMING', installation_delay: 'ROAMING',
  cancellation_request: 'CANCELLATION', formal_complaint: 'CANCELLATION',
};
const INTENT_NAME: Record<IntentKey, string> = { BILLING: 'Billing', ROAMING: 'Roaming', CANCELLATION: 'Cancellation' };
/** The demo scenarios have only a card (profile, difficulty, title). */
const BY_PROFILE: Record<string, PersonaKey> = { New: 'NEW_SUBSCRIBER', Loyal: 'LOYAL_AT_RISK', Unsatisfied: 'IMPATIENT', Premium: 'ANGRY_PREMIUM', 'At risk': 'LOYAL_AT_RISK' };
const BY_LABEL: Record<string, DifficultyKey> = { Easy: 'EASY', Medium: 'MEDIUM', Hard: 'HARD' };

const level = (n: number): DifficultyKey => (n <= 2 ? 'EASY' : n === 3 ? 'MEDIUM' : 'HARD');
const intentFromTitle = (title: string): IntentKey => (/\b(roaming|abroad|signal|internet|line)\b/i.test(title) ? 'ROAMING' : /cancel|complain|leave/i.test(title) ? 'CANCELLATION' : 'BILLING');

export function simSettings(s: ScenarioDetail): SimSettings {
  const why: string[] = [];
  const spec = s.spec;
  const persona = (spec ? BY_SEGMENT[spec.segment] : BY_PROFILE[s.profile]) ?? 'IMPATIENT';
  why.push(`Customer: ${spec ? `a ${spec.segment.replace('_', ' ')} customer` : `profile ${s.profile}`} becomes “${LABEL[persona]}”.`);
  let mix: PersonaKey | null = null;
  if ((s.opening_emotion === 'fear' || s.opening_emotion === 'sad') && persona !== 'ANXIOUS') {
    mix = 'ANXIOUS';
    why.push(`The customer starts ${s.opening_emotion === 'fear' ? 'afraid' : 'sad'}: mixed with “${LABEL.ANXIOUS}”.`);
  }
  const intent = (spec?.intent ? BY_INTENT[spec.intent] : undefined) ?? intentFromTitle(s.title);
  why.push(`Reason for the call: ${spec?.intent ? spec.intent.replace(/_/g, ' ') : 'read from the title'} becomes “${INTENT_NAME[intent]}”, the closest of the simulator's three reasons.`);
  const difficulty = spec ? level(spec.difficulty) : (BY_LABEL[s.difficulty] ?? 'MEDIUM');
  why.push(`Difficulty ${spec ? `${spec.difficulty}/5` : s.difficulty} becomes “${difficulty[0] + difficulty.slice(1).toLowerCase()}”.`);
  const memory = !!spec?.events?.includes('repeat_caller');
  if (memory) why.push('The customer is a repeat caller: the call starts as a repeat contact.');
  return { persona, mix, difficulty, intent, memory, why };
}
