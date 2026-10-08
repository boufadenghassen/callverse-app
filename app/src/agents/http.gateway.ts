import { Injectable } from '@nestjs/common';
import { AgentDownError, AgentGateway } from './agent.gateway';
import * as m from './models';

/**
 * Calls the Python agents over HTTP (AGENTS_MODE=http). Every path variable is encoded, so user input
 * can never change the path or inject query parameters. Read-only data is cached for 30 seconds.
 */
@Injectable()
export class HttpAgentGateway extends AgentGateway {
  private readonly base = process.env.CALLVERSE_AGENTS_URL ?? 'http://localhost:8000';
  private readonly cache = new Map<string, { at: number; value: unknown }>();

  private async call<T>(path: string, body?: unknown, cacheable = false): Promise<T> {
    const hit = this.cache.get(path);
    if (cacheable && hit && Date.now() - hit.at < 30_000) return hit.value as T;
    let res: Response;
    try {
      res = await fetch(this.base + path, {
        method: body === undefined ? 'GET' : 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(5000),
      });
    } catch (e) {
      throw new AgentDownError(String(e));
    }
    if (!res.ok) throw new AgentDownError(`${path} answered ${res.status}`);
    const value = (await res.json()) as T;
    if (cacheable) this.cache.set(path, { at: Date.now(), value });
    return value;
  }

  customerContext(id: string) { return this.call<m.CustomerContext>(`/advisor/customers/${encodeURIComponent(id)}`); }
  suggestAnswer(customerId: string, query: string) { return this.call<m.SuggestedAnswer>('/advisor/suggest', { customer_id: customerId, query }); }
  forecast(queue: string) { return this.call<m.ForecastPoint[]>(`/workforce/forecast?queue=${encodeURIComponent(queue)}`, undefined, true); }
  simulate(r: m.SimulationRequest) { return this.call<m.SimulationResult>('/workforce/simulate', r); }
  recentReviews() { return this.call<m.QualityReview[]>('/quality/reviews?limit=20', undefined, true); }
  openComplaints() { return this.call<m.ComplaintCase[]>('/complaints/open', undefined, true); }
  scenarios() { return this.call<m.Scenario[]>('/training/scenarios', undefined, true); }
  opportunities() { return this.call<m.Opportunity[]>('/sales/opportunities', undefined, true); }
}
