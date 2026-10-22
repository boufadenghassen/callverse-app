import * as m from './models';

/** Raised when an agent service cannot be reached; shown as a friendly 503 page. */
export class AgentDownError extends Error {}
/** The call id is not known to the customer simulator. */
export class UnknownCallError extends Error {}
/** No customer exists with that id. */
export class CustomerNotFoundError extends Error {}
/** No neural voice is available (demo mode, or the voice model is not installed): the page falls back to the browser's voice. */
export class VoiceUnavailableError extends Error {}
/** The recording cannot be used (unreadable, silent, too short); the message is safe to show. */
export class BadAudioError extends Error {}
/** A request the quality agent refused (nothing to review, not two channels...); the message is safe to show. */
export class RejectedError extends Error {}
/** The feature needs the real Python agents (AGENTS_MODE=http); the demo data cannot do it. */
export class NeedsRealAgentsError extends Error {}

/**
 * Single entry point from the web layer to the seven agents. The UI never talks to an agent directly,
 * so swapping mock data for the real Python services is an environment change (AGENTS_MODE=http), not a code change.
 */
export abstract class AgentGateway {
  /** Throws CustomerNotFoundError when no customer has that id. */
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
  /** Lunch breaks and overtime for a typical day. */
  abstract schedule(): Promise<m.SchedulePlan>;
  abstract forecast(queue: string): Promise<m.ForecastPoint[]>;
  abstract simulate(request: m.SimulationRequest): Promise<m.SimulationResult>;
  abstract recentReviews(filter?: m.ReviewFilter): Promise<m.QualityReview[]>;
  /** How accurate the analyst is on labelled calls; null when the demo data is used. */
  abstract qualityEvaluation(): Promise<m.QualityEvaluation | null>;
  /** A reviewer's verdict on one finding. Throws RejectedError (no such finding) or NeedsRealAgentsError. */
  abstract qualityFeedback(callId: string, rule: string, turn: number, verdict: 'agree' | 'disagree' | 'clear', by: string): Promise<m.QualityReview>;
  abstract qualityReview(callId: string): Promise<m.QualityReview | null>;
  abstract qualityAnalytics(): Promise<m.QualityAnalytics>;
  /** Score a live call (a customer simulator session). Throws UnknownCallError, RejectedError or NeedsRealAgentsError. */
  abstract reviewCall(callId: string, advisor: string): Promise<m.QualityReview>;
  /** Score a two-channel recording (advisor left, customer right). Throws BadAudioError, RejectedError, VoiceUnavailableError or NeedsRealAgentsError. */
  abstract reviewAudio(audio: Buffer, advisor: string): Promise<m.QualityReview>;
  /** A two-channel example call (WAV). */
  abstract sampleCall(): Promise<Buffer>;
  abstract openComplaints(): Promise<m.ComplaintCase[]>;
  abstract scenarios(): Promise<m.Scenario[]>;
  abstract opportunities(): Promise<m.Opportunity[]>;
  /** The needs a customer voiced in a conversation and the offers that answer them, with the reasons. Throws NeedsRealAgentsError (demo mode) or RejectedError (unknown customer). */
  abstract salesDetect(customerId: string | null, turns: m.SalesTurn[]): Promise<m.SalesDetection>;
  /** What happened to an offer that was made. Throws NeedsRealAgentsError or RejectedError. */
  abstract salesOutcome(outcome: m.SalesOutcome): Promise<void>;
  abstract salesAnalytics(): Promise<m.SalesAnalytics | null>;
  /** What a month of calls would earn under a selling rule, replayed on the history. Throws NeedsRealAgentsError (demo mode) or RejectedError. */
  abstract salesSimulate(request: m.SalesSimulationRequest): Promise<m.SalesSimulation>;
}
