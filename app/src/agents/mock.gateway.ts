import { Injectable } from '@nestjs/common';
import { randomBytes } from 'node:crypto';
import { DifficultyKey, IntentKey, MOVES, MoveKey, PersonaKey, PERSONAS, replay } from '../pages/client-simulator';
import { readAdvisor } from '../pages/customer-llm';
import { AgentGateway, NeedsRealAgentsError, UnknownCallError, VoiceUnavailableError } from './agent.gateway';
import * as m from './models';

interface Call { cfg: m.CallConfig; moves: MoveKey[]; said: string[] }
const MAX_CALLS = 200; // ponytail: oldest call is dropped past this

/** Realistic fake data so the UI can be built and demoed before the agents are ready. */
@Injectable()
export class MockAgentGateway extends AgentGateway {
  async customerContext(id: string): Promise<m.CustomerContext> {
    return { id, name: 'Yasmine Toumi', profile: 'Loyal customer, 6 years', intents: ['Billing', 'Plan change'],
      contract: 'Mobile Plus 40 GB', openTickets: 1, transfers: 1, mood: 'Impatient' };
  }

  async suggestAnswer(_customerId?: string, _query?: string): Promise<m.SuggestedAnswer> {
    return {
      text: "I can see the double charge on your September bill. I've opened a refund for the duplicate amount; "
        + "it will appear on your next statement. I'm also noting your plan-change request so you won't need to explain it again.",
      sources: ['Billing policy §4.2', 'Refund procedure v3'],
      policyWarning: 'Refunds above 50 TND need supervisor approval.', confidence: 0.86,
    };
  }

  private readonly calls = new Map<string, Call>();
  private replayOf(c: Call) {
    const { persona, mix, difficulty, intent, memory } = c.cfg;
    return replay(persona as PersonaKey, mix as PersonaKey | null, difficulty as DifficultyKey, intent as IntentKey, memory, c.moves, c.said);
  }

  /** The simulated customer, same engine as the training page; the Python agent replaces it in http mode. */
  async startCall(cfg: m.CallConfig): Promise<m.CallStart> {
    if (this.calls.size >= MAX_CALLS) this.calls.delete(this.calls.keys().next().value!);
    const id = randomBytes(8).toString('hex'), call: Call = { cfg, moves: [], said: [] };
    this.calls.set(id, call);
    const r = this.replayOf(call);
    return { id, persona: PERSONAS[cfg.persona as PersonaKey].label, opening: r.opening, mood: r.mood, patience: r.patience };
  }

  async say(id: string, text: string): Promise<m.CallReply> {
    const call = this.calls.get(id);
    if (!call) throw new UnknownCallError(id);
    const before = this.replayOf(call);
    if (before.outcome) return { ended: true, outcome: before.outcome, mood: before.mood, patience: before.patience, client: null, move: null, moveLabel: null };
    const move = readAdvisor(text);
    call.moves.push(move); call.said.push(text);
    const r = this.replayOf(call), t = r.turns[r.turns.length - 1];
    return { ended: !!r.outcome, outcome: r.outcome, mood: t.mood, patience: t.patience, client: t.client, move, moveLabel: MOVES[move].label };
  }

  async speak(_request: m.SpeakRequest): Promise<Buffer> {
    throw new VoiceUnavailableError('demo mode has no neural voice');
  }

  async schedule(): Promise<m.SchedulePlan> {
    return {
      baselineSla: 0.82, plannedSla: 0.85, idealSla: 0.77, overtimeHours: 1, method: 'Demo data: the real workforce agent places lunches with Erlang C.',
      queues: [{ queue: 'A', name: 'Billing', advisors: 10, onLunch: 8, idealSla: 0.73, baselineSla: 0.81, plannedSla: 0.82, worstBaseline: { hour: '12h', sla: 0.5 }, worstPlanned: { hour: '13h', sla: 0.59 },
        lunchHours: [{ hour: '11h', naive: 0, planned: 2, onDuty: 8 }, { hour: '12h', naive: 8, planned: 2, onDuty: 9 }, { hour: '13h', naive: 0, planned: 3, onDuty: 10 }, { hour: '14h', naive: 0, planned: 1, onDuty: 10 }] }],
      overtime: [{ queue: 'A', hour: '13h', advisors: 1, sla: 0.59, calls: 73, text: 'Queue A at 13h: 1 advisor on overtime for that hour (demo data).' }],
    };
  }

  async routing(): Promise<m.RoutingPlan> {
    const q = (queue: string, name: string, calls: number, advisors: number, recommended: number, b: number, r: number): m.RoutingQueue =>
      ({ queue, name, calls, priority: 1, advisors, recommended, baselineSla: b, recommendedSla: r, baselineWaitSec: 0, recommendedWaitSec: 0 });
    return {
      baselineSla: 0.7, optimizedSla: 0.78, moves: 1, method: 'Demo data: the real workforce agent computes this with Erlang C and a local search.',
      hours: [{ hour: '14h', queues: [q('A', 'Billing', 91, 8, 9, 0.47, 0.71), q('B', 'Plans and billing, premium', 81, 8, 8, 0.49, 0.49), q('C', 'Roaming', 26, 5, 4, 0.87, 0.67)],
        moves: [{ advisor: 'C02', skills: ['C', 'D', 'A'], fromQueue: 'C', toQueue: 'A', gain: 17, text: 'Move C02 (skills C, D, A) from queue C to queue A at 14h: queue A goes from 47% to 71% within 20 s, queue C from 87% to 67%.' }] }],
    };
  }

  async transcribe(_audio: Buffer): Promise<m.Transcript> {
    throw new VoiceUnavailableError('demo mode cannot transcribe');
  }

  async forecast(_queue?: string): Promise<m.ForecastPoint[]> {
    // [hour, actual, forecast]; actual is null for hours not reached yet
    const rows: [string, number | null, number][] = [['9h', 20, 22], ['10h', 28, 30], ['11h', 40, 42], ['12h', 52, 55], ['13h', 60, 64],
      ['14h', null, 72], ['15h', null, 60], ['16h', null, 45], ['17h', null, 35]];
    return rows.map(([hour, actual, forecast]) => ({ hour, actual, forecast }));
  }

  async simulate(r: m.SimulationRequest): Promise<m.SimulationResult> {
    const baseline = 240;
    return {
      baselineWaitSec: baseline, simulatedWaitSec: Math.max(20, baseline - r.extraAdvisors * 55),
      baselineSla: 0.71, simulatedSla: Math.min(0.98, 0.71 + r.extraAdvisors * 0.06),
      recommendations: ['Move 2 billing-skilled advisors from queue A (forecast below capacity)',
        'Shift one break from 14:30 to 16:15', 'Offer a callback when the wait passes 3 minutes'],
    };
  }

  async qualityReview(callId: string): Promise<m.QualityReview | null> {
    return (await this.recentReviews()).find((r) => r.callId === callId) ?? null;
  }

  async qualityAnalytics(): Promise<m.QualityAnalytics> {
    const crit = { Accuracy: 8.5, Compliance: 7, Communication: 9, Resolution: 7.5 };
    return {
      method: 'Demo data: the real quality agent scores every stored call.',
      team: { calls: 2, avgOverall: 75, avgByCriterion: crit, weeks: [null, null, null, null, null, null, 62, 88], causes: [{ cause: 'Process skipped', calls: 1, share: 1 }], byIntent: [{ intent: 'Billing', calls: 2, avg: 75 }],
        topErrors: [{ rule: 'promise_before_check', label: 'Promise before the policy check', calls: 1, share: 0.5, cause: 'Process skipped' }] },
      advisors: [{ advisor: 'Karim B.', calls: 1, avgOverall: 62, vsTeam: -13, avgByCriterion: crit, weeks: [null, null, null, null, null, null, null, 62], trend: null,
        weakest: { criterion: 'Compliance', avg: 4 }, strongest: { criterion: 'Communication', avg: 9 },
        topErrors: [{ rule: 'promise_before_check', label: 'Promise before the policy check', calls: 1, share: 1, cause: 'Process skipped' }],
        coaching: [{ rule: 'promise_before_check', label: 'Promise before the policy check', calls: 1, tip: 'Check the policy before promising anything.', scenario: 'Double charge, customer asks for an immediate refund' }], lastCalls: ['CALL-3381'] }],
    };
  }

  async reviewCall(_callId: string, _advisor: string): Promise<m.QualityReview> {
    throw new NeedsRealAgentsError('demo mode cannot review live calls');
  }

  async reviewAudio(_audio: Buffer, _advisor: string): Promise<m.QualityReview> {
    throw new NeedsRealAgentsError('demo mode cannot review recordings');
  }

  async sampleCall(): Promise<Buffer> {
    throw new NeedsRealAgentsError('demo mode has no sample call');
  }

  async qualityEvaluation(): Promise<m.QualityEvaluation | null> {
    return null;
  }

  async qualityFeedback(_callId: string, _rule: string, _turn: number, _verdict: 'agree' | 'disagree' | 'clear', _by: string): Promise<m.QualityReview> {
    throw new NeedsRealAgentsError('demo mode keeps no verdicts');
  }

  async recentReviews(_filter?: m.ReviewFilter): Promise<m.QualityReview[]> {
    return [
      { callId: 'CALL-3381', advisor: 'Karim B.', overall: 62, criteria: [
          { name: 'Accuracy', score: 8, max: 10, evidence: 'Correct refund amount quoted', timestamp: '01:12' },
          { name: 'Compliance', score: 4, max: 10, evidence: 'Promised a refund before checking the approval policy', timestamp: '02:41' },
          { name: 'Communication', score: 9, max: 10, evidence: 'Acknowledged frustration before answering', timestamp: '00:35' },
          { name: 'Resolution', score: 5, max: 10, evidence: 'Plan change left open, no follow-up set', timestamp: '04:02' }],
        counterfactual: 'If the refund approval had been checked first, compliance would have passed (+5).' },
      { callId: 'CALL-3379', advisor: 'Hela M.', overall: 88, criteria: [
          { name: 'Accuracy', score: 9, max: 10, evidence: 'Right plan details given', timestamp: '00:58' },
          { name: 'Compliance', score: 10, max: 10, evidence: 'Identity verified before account access', timestamp: '00:20' },
          { name: 'Communication', score: 8, max: 10, evidence: 'Some jargon with a new customer', timestamp: '01:45' },
          { name: 'Resolution', score: 9, max: 10, evidence: 'Issue closed on first contact', timestamp: '03:10' }],
        counterfactual: "Replacing 'APN settings' with plain wording would lift communication to 10." },
    ];
  }

  async openComplaints(): Promise<m.ComplaintCase[]> {
    return [
      { id: 'CMP-221', summary: 'Charged twice, third contact this month', severity: 'Critical', escalationRisk: 87, cluster: 'Billing duplicates', hoursLeft: 6 },
      { id: 'CMP-219', summary: 'Roaming bundle not applied abroad', severity: 'High', escalationRisk: 64, cluster: 'Roaming activation', hoursLeft: 20 },
      { id: 'CMP-214', summary: 'Contract cancellation fee disputed', severity: 'Medium', escalationRisk: 41, cluster: 'Contract terms', hoursLeft: 46 },
    ];
  }

  async scenarios(): Promise<m.Scenario[]> {
    return [
      { id: 'SC-31', title: 'Double charge, customer threatens to post online', profile: 'Unsatisfied', difficulty: 'Hard', origin: 'QA weakness: compliance' },
      { id: 'SC-30', title: 'First call from a new subscriber about data limits', profile: 'New', difficulty: 'Easy', origin: 'Template library' },
      { id: 'SC-29', title: 'Premium customer, two intents, transferred once', profile: 'Premium', difficulty: 'Medium', origin: 'What-if mutation' },
    ];
  }

  async opportunities(): Promise<m.Opportunity[]> {
    return [
      { customer: 'Mounir Sassi', offer: 'Family bundle', relevance: 82, reason: 'Asked twice about adding a line' },
      { customer: 'Salma Hammami', offer: 'Loyalty data top-up', relevance: 71, reason: 'Usage dropping, churn risk; retention offer' },
    ];
  }
}
