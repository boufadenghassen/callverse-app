import { Injectable } from '@nestjs/common';
import { AgentDownError, UnknownCallError } from './agent.gateway';
import { MockAgentGateway } from './mock.gateway';
import * as m from './models';

/**
 * Calls the Python agents over HTTP (AGENTS_MODE=http). It starts from the demo data and replaces only the agents that
 * exist in services/agents (advisor suggestions, customer simulator); the rest stay demo until their Python agent is built.
 * Every path variable is encoded, so user input can never change the path or inject query parameters.
 */
@Injectable()
export class HttpAgentGateway extends MockAgentGateway {
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
    if (res.status === 404 && path.startsWith('/customer/sessions/')) throw new UnknownCallError(path);
    if (!res.ok) throw new AgentDownError(`${path} answered ${res.status}`);
    const value = (await res.json()) as T;
    if (cacheable) this.cache.set(path, { at: Date.now(), value });
    return value;
  }

  /** Real Python agents: the advisor and the customer simulator. */
  suggestAnswer(customerId: string, query: string) { return this.call<m.SuggestedAnswer>('/advisor/suggest', { customer_id: customerId, query }); }
  startCall(c: m.CallConfig) { return this.call<m.CallStart>('/customer/sessions', c); }
  say(callId: string, text: string) { return this.call<m.CallReply>(`/customer/sessions/${encodeURIComponent(callId)}/say`, { text }); }
}
