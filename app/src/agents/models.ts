export interface CustomerContext { id: string; name: string; profile: string; intents: string[]; contract: string; openTickets: number; transfers: number; mood: string }
export interface Evidence { source: string; score: number; excerpt: string }
/** `intents` and `evidence` come from the real advisor agent; the demo data leaves them out. */
export interface SuggestedAnswer { text: string; sources: string[]; policyWarning: string | null; confidence: number; intents?: string[]; evidence?: Evidence[] }
export interface Transcript { text: string; seconds: number }
export interface SpeakRequest { text: string; role: 'advisor' | 'customer'; persona: string | null; mood: number }
/** A live call with the simulated customer: `moveLabel` says how the customer's agent read the advisor's last reply. */
export interface CallConfig { persona: string; mix: string | null; difficulty: string; intent: string; memory: boolean }
export interface CallStart { id: string; persona: string; opening: string; mood: number; patience: number }
export interface CallOutcome { verdict: string; expectationMet: boolean; churnRisk: number; effort: number; notes: string[] }
export interface CallReply { ended: boolean; outcome: CallOutcome | null; mood: number; patience: number; client: string | null; move: string | null; moveLabel: string | null }
/** `actual` is null for hours not reached yet. */
export interface ForecastPoint { hour: string; actual: number | null; forecast: number }
export interface SimulationRequest { queue: string; extraAdvisors: number; from: string; to: string }
/** One hour of a simulation, so the numbers can be checked (the real workforce agent fills `hours` and `method`). */
export interface SimulationHour { hour: string; calls: number; advisors: number; simulatedAdvisors: number; baselineWaitSec: number; simulatedWaitSec: number; baselineSla: number; simulatedSla: number; needed: number }
export interface SimulationResult { baselineWaitSec: number; simulatedWaitSec: number; baselineSla: number; simulatedSla: number; recommendations: string[]; hours?: SimulationHour[]; method?: string }
export interface CriterionScore { name: string; score: number; max: number; evidence: string; timestamp: string }
export interface QualityReview { callId: string; advisor: string; overall: number; criteria: CriterionScore[]; counterfactual: string }
/** `reasons`, `route` and the rest come from the real complaint agent; the demo data leaves them out. `escalationRisk` is a rule-based priority 0-100, not a probability. */
export interface ComplaintCase { id: string; summary: string; severity: string; escalationRisk: number; cluster: string; hoursLeft: number;
  overdue?: boolean; reasons?: string[]; route?: string; status?: string; channel?: string; state?: string; onBehalf?: boolean; owner?: string | null }
export interface ComplaintTopic { topic: string; cases: number; open: number; share: number; unresolvedPct: number; trendPct: number | null;
  byMonth: Record<string, number>; hotspots: { state: string; cases: number }[]; keywords: string[]; example: string }
export interface ComplaintDiscovered { cluster: number; cases: number; keywords: string[]; closestTopic: string; agreementPct: number }
export interface ComplaintClusters { topics: ComplaintTopic[]; discovered: ComplaintDiscovered[] }
export interface Scenario { id: string; title: string; profile: string; difficulty: string; origin: string }
export interface Opportunity { customer: string; offer: string; relevance: number; reason: string }
