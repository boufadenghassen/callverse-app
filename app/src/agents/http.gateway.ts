import { Injectable } from '@nestjs/common';
import { AgentDownError, BadAudioError, CustomerNotFoundError, RejectedError, UnknownCallError, VoiceUnavailableError } from './agent.gateway';
import { MockAgentGateway } from './mock.gateway';
import * as m from './models';

/**
 * Calls the Python agents over HTTP (AGENTS_MODE=http). It starts from the demo data and replaces only the agents that
 * exist in services/agents (advisor suggestions, customer simulator, workforce forecast and simulation, voice); the rest stay demo until their Python agent is built.
 * Every path variable is encoded, so user input can never change the path or inject query parameters.
 */
@Injectable()
export class HttpAgentGateway extends MockAgentGateway {
  private readonly base = process.env.CALLVERSE_AGENTS_URL ?? 'http://localhost:8000';
  private readonly cache = new Map<string, { at: number; value: unknown }>();

  private async call<T>(path: string, body?: unknown, cacheable = false, method?: 'GET' | 'POST' | 'DELETE'): Promise<T> {
    const hit = this.cache.get(path);
    if (cacheable && hit && Date.now() - hit.at < 30_000) return hit.value as T;
    let res: Response;
    try {
      res = await fetch(this.base + path, {
        method: method ?? (body === undefined ? 'GET' : 'POST'),
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(5000),
      });
    } catch (e) {
      throw new AgentDownError(String(e));
    }
    if (res.status === 404 && path.startsWith('/customer/sessions/')) throw new UnknownCallError(path);
    if (res.status === 404 && path.startsWith('/advisor/customers/')) throw new CustomerNotFoundError(path);
    if (!res.ok) throw new AgentDownError(`${path} answered ${res.status}`);
    if (res.status === 204) return undefined as T;
    const value = (await res.json()) as T;
    if (cacheable) this.cache.set(path, { at: Date.now(), value });
    return value;
  }

  /** Real Python agents: the advisor, the customer simulator, the workforce manager, the voice. */
  customerContext(customerId: string) { return this.call<m.CustomerContext>(`/advisor/customers/${encodeURIComponent(customerId)}`, undefined, true); }
  suggestAnswer(customerId: string, query: string) { return this.call<m.SuggestedAnswer>('/advisor/suggest', { customer_id: customerId, query }); }
  async speak(r: m.SpeakRequest): Promise<Buffer> {
    let res: Response;
    try {
      res = await fetch(`${this.base}/voice/speak`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(r),
        signal: AbortSignal.timeout(60_000),   // the first sentence loads the voice model
      });
    } catch (e) {
      throw new AgentDownError(String(e));
    }
    if (res.status === 503) throw new VoiceUnavailableError('the neural voice is not installed');
    if (!res.ok) throw new AgentDownError(`/voice/speak answered ${res.status}`);
    return Buffer.from(await res.arrayBuffer());
  }
  async transcribe(audio: Buffer): Promise<m.Transcript> {
    let res: Response;
    try {
      res = await fetch(`${this.base}/voice/transcribe`, { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: new Uint8Array(audio), signal: AbortSignal.timeout(60_000) });
    } catch (e) {
      throw new AgentDownError(String(e));
    }
    if (res.status === 503) throw new VoiceUnavailableError('the speech-to-text model is not installed');
    if (res.status === 400) throw new BadAudioError(((await res.json().catch(() => ({}))) as { detail?: string }).detail ?? 'Could not use this recording.');
    if (!res.ok) throw new AgentDownError(`/voice/transcribe answered ${res.status}`);
    return (await res.json()) as m.Transcript;
  }
  recentReviews(f: m.ReviewFilter = {}) {   // not cached: a new review or a verdict must show at once
    const q = [f.advisor && `advisor=${encodeURIComponent(f.advisor)}`, f.rule && `rule=${encodeURIComponent(f.rule)}`, f.below && `below=${f.below}`].filter(Boolean).join('&');
    return this.call<m.QualityReview[]>(`/quality/reviews?limit=${f.advisor || f.rule || f.below ? 100 : 20}${q ? `&${q}` : ''}`);
  }
  qualityEvaluation() { return this.call<m.QualityEvaluation>('/quality/evaluation', undefined, true); }
  async qualityFeedback(callId: string, rule: string, turn: number, verdict: 'agree' | 'disagree' | 'clear', by: string) {
    const res = await this.raw('/quality/feedback', { callId, rule, turn, verdict, by });
    if (res.status === 404 || res.status === 422) throw new RejectedError('There is no such finding to check.');
    if (!res.ok) throw new AgentDownError(`quality feedback answered ${res.status}`);
    return (await res.json()) as m.QualityReview;
  }
  async qualityReview(callId: string) {
    try { return await this.call<m.QualityReview>(`/quality/reviews/${encodeURIComponent(callId)}`); } catch (e) { if (e instanceof AgentDownError && /answered 404/.test(e.message)) return null; throw e; }
  }
  qualityAnalytics() { return this.call<m.QualityAnalytics>('/quality/analytics'); }
  async reviewCall(callId: string, advisor: string) {
    const res = await this.raw('/quality/review-call', { callId, advisor });
    if (res.status === 404) throw new UnknownCallError(callId);
    return this.review(res);
  }
  async reviewAudio(audio: Buffer, advisor: string) {
    const res = await this.raw(`/quality/review-audio?advisor=${encodeURIComponent(advisor)}`, audio);
    if (res.status === 503) throw new VoiceUnavailableError('the speech-to-text model is not installed');
    return this.review(res);
  }
  async sampleCall() {
    const res = await this.raw('/quality/sample-call.wav');
    if (res.status === 503) throw new VoiceUnavailableError('the neural voice is not installed');
    if (!res.ok) throw new AgentDownError(`sample call answered ${res.status}`);
    return Buffer.from(await res.arrayBuffer());
  }
  /** A request whose answer can be a refusal with a message (400, 422) or a long wait (speech to text on a recording). */
  private async raw(path: string, body?: unknown): Promise<Response> {
    const binary = Buffer.isBuffer(body);
    try {
      return await fetch(this.base + path, {
        method: body === undefined ? 'GET' : 'POST', signal: AbortSignal.timeout(180_000),
        headers: { 'Content-Type': binary ? 'application/octet-stream' : 'application/json' },
        body: body === undefined ? undefined : binary ? new Uint8Array(body as Buffer) : JSON.stringify(body),
      });
    } catch (e) {
      throw new AgentDownError(String(e));
    }
  }
  private async review(res: Response): Promise<m.QualityReview> {
    if (res.status === 400 || res.status === 422) {
      const detail = ((await res.json().catch(() => ({}))) as { detail?: string | unknown[] }).detail;
      throw new BadAudioError(typeof detail === 'string' ? detail : 'This could not be reviewed.');
    }
    if (!res.ok) throw new AgentDownError(`quality agent answered ${res.status}`);
    return (await res.json()) as m.QualityReview;
  }
  schedule() { return this.call<m.SchedulePlan>('/workforce/schedule', undefined, true); }
  routing() { return this.call<m.RoutingPlan>('/workforce/routing', undefined, true); }
  forecast(queue: string) { return this.call<m.ForecastPoint[]>(`/workforce/forecast?queue=${encodeURIComponent(queue)}`, undefined, true); }
  simulate(r: m.SimulationRequest) { return this.call<m.SimulationResult>('/workforce/simulate', r); }
  opportunities() { return this.call<m.Opportunity[]>('/sales/opportunities'); }
  salesAnalytics() { return this.call<m.SalesAnalytics>('/sales/analytics'); }
  async salesDetect(customerId: string | null, turns: m.SalesTurn[]) {
    const res = await this.raw('/sales/detect', { customer_id: customerId, turns });
    if (res.status === 404 || res.status === 422) throw new RejectedError('The conversation or the customer is not valid.');
    if (!res.ok) throw new AgentDownError(`sales detect answered ${res.status}`);
    return (await res.json()) as m.SalesDetection;
  }
  async salesOutcome(o: m.SalesOutcome) {
    const res = await this.raw('/sales/outcome', { customer_id: o.customerId, offer_id: o.offerId, outcome: o.outcome, relevance: o.relevance, cue: o.cue, need: o.need });
    if (res.status === 404 || res.status === 422) throw new RejectedError('This offer or customer is not valid.');
    if (!res.ok) throw new AgentDownError(`sales outcome answered ${res.status}`);
  }
  startCall(c: m.CallConfig) { return this.call<m.CallStart>('/customer/sessions', c); }
  say(callId: string, text: string) { return this.call<m.CallReply>(`/customer/sessions/${encodeURIComponent(callId)}/say`, { text }); }
  scenarios() { return this.call<m.Scenario[]>('/training/scenarios', undefined, true); }
  scenario(id: string) { return this.call<m.ScenarioDetail>(`/scenario-gen/scenarios/${encodeURIComponent(id)}`); }
  scenarioLineage(id: string) { return this.call<m.ScenarioDetail[]>(`/scenario-gen/scenarios/${encodeURIComponent(id)}/lineage`); }
  replayScenario(id: string) { return this.call<m.ScenarioDetail>(`/scenario-gen/scenarios/${encodeURIComponent(id)}/replay`, {}); }
  mutateScenario(id: string, operation: 'harder' | 'easier' | 'add_second_problem') {
    return this.call<m.ScenarioDetail>(`/scenario-gen/scenarios/${encodeURIComponent(id)}/mutate`, { ops: [{ op: operation }] });
  }
  async deleteScenario(id: string): Promise<void> {
    await this.call<void>(`/scenario-gen/scenarios/${encodeURIComponent(id)}`, undefined, false, 'DELETE');
  }
  trainingPlan(advisorId: string, weaknesses: m.TrainingWeakness[]) {
    return this.call<m.TrainingPlan>('/scenario-gen/training-plan', {
      advisor_id: advisorId,
      weaknesses,
      size: 6,
      current_level: 2,
    });
  }
}
