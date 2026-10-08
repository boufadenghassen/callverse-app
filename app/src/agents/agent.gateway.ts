import * as m from './models';

/** Raised when an agent service cannot be reached; shown as a friendly 503 page. */
export class AgentDownError extends Error {}

/**
 * Single entry point from the web layer to the seven agents. The UI never talks to an agent directly,
 * so swapping mock data for the real Python services is an environment change (AGENTS_MODE=http), not a code change.
 */
export abstract class AgentGateway {
  abstract customerContext(customerId: string): Promise<m.CustomerContext>;
  abstract suggestAnswer(customerId: string, query: string): Promise<m.SuggestedAnswer>;
  abstract forecast(queue: string): Promise<m.ForecastPoint[]>;
  abstract simulate(request: m.SimulationRequest): Promise<m.SimulationResult>;
  abstract recentReviews(): Promise<m.QualityReview[]>;
  abstract openComplaints(): Promise<m.ComplaintCase[]>;
  abstract scenarios(): Promise<m.Scenario[]>;
  abstract opportunities(): Promise<m.Opportunity[]>;
}
