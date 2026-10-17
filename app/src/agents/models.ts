export interface CustomerContext { id: string; name: string; profile: string; intents: string[]; contract: string; openTickets: number; transfers: number; mood: string }
export interface Evidence { source: string; score: number; excerpt: string }
/** `intents` and `evidence` come from the real advisor agent; the demo data leaves them out. */
export interface SuggestedAnswer { text: string; sources: string[]; policyWarning: string | null; confidence: number; intents?: string[]; evidence?: Evidence[] }
export interface SpeakRequest { text: string; role: 'advisor' | 'customer'; persona: string | null; mood: number }
/** A live call with the simulated customer: `moveLabel` says how the customer's agent read the advisor's last reply. */
export interface CallConfig { persona: string; mix: string | null; difficulty: string; intent: string; memory: boolean }
export interface CallStart { id: string; persona: string; opening: string; mood: number; patience: number }
export interface CallOutcome { verdict: string; expectationMet: boolean; churnRisk: number; effort: number; notes: string[] }
export interface CallReply { ended: boolean; outcome: CallOutcome | null; mood: number; patience: number; client: string | null; move: string | null; moveLabel: string | null }
/** `actual` is null for hours not reached yet. */
export interface ForecastPoint { hour: string; actual: number | null; forecast: number }
export interface SimulationRequest { queue: string; extraAdvisors: number; from: string; to: string }
export interface SimulationResult { baselineWaitSec: number; simulatedWaitSec: number; baselineSla: number; simulatedSla: number; recommendations: string[] }
export interface CriterionScore { name: string; score: number; max: number; evidence: string; timestamp: string }
export interface QualityReview { callId: string; advisor: string; overall: number; criteria: CriterionScore[]; counterfactual: string }
export interface ComplaintCase { id: string; summary: string; severity: string; escalationRisk: number; cluster: string; hoursLeft: number }
export interface Scenario { id: string; title: string; profile: string; difficulty: string; origin: string }
export interface Opportunity { customer: string; offer: string; relevance: number; reason: string }
