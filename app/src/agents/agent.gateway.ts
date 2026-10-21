import * as m from './models';

/** Raised when an agent service cannot be reached; shown as a friendly 503 page. */
export class AgentDownError extends Error {}
/** The call id is not known to the customer simulator. */
export class UnknownCallError extends Error {}
/** No neural voice is available (demo mode, or the voice model is not installed): the page falls back to the browser's voice. */
export class VoiceUnavailableError extends Error {}
/** The recording cannot be used (unreadable, silent, too short); the message is safe to show. */
export class BadAudioError extends Error {}

/**
 * Single entry point from the web layer to the seven agents. The UI never talks to an agent directly,
 * so swapping mock data for the real Python services is an environment change (AGENTS_MODE=http), not a code change.
 */
export abstract class AgentGateway {
  abstract customerContext(customerId: string): Promise<m.CustomerContext>;
  abstract suggestAnswer(customerId: string, query: string): Promise<m.SuggestedAnswer>;
  abstract startCall(config: m.CallConfig): Promise<m.CallStart>;
  /** Throws UnknownCallError when the call id is not known (for example the agents service restarted). */
  abstract say(callId: string, text: string): Promise<m.CallReply>;
  /** The text as WAV audio. Throws VoiceUnavailableError when no neural voice exists. */
  abstract speak(request: m.SpeakRequest): Promise<Buffer>;
  /** A voice note (16 kHz mono WAV) as text. Throws VoiceUnavailableError or BadAudioError. */
  abstract transcribe(audio: Buffer): Promise<m.Transcript>;
  /** Skill-based reassignment of advisors between queues for the hours still to come today. */
  abstract routing(): Promise<m.RoutingPlan>;
  abstract forecast(queue: string): Promise<m.ForecastPoint[]>;
  abstract simulate(request: m.SimulationRequest): Promise<m.SimulationResult>;
  abstract recentReviews(): Promise<m.QualityReview[]>;
  abstract openComplaints(): Promise<m.ComplaintCase[]>;
  abstract scenarios(): Promise<m.Scenario[]>;
  abstract opportunities(): Promise<m.Opportunity[]>;
}
