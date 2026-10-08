export interface CustomerContext { id: string; name: string; profile: string; intents: string[]; contract: string; openTickets: number; transfers: number; mood: string }
export interface SuggestedAnswer { text: string; sources: string[]; policyWarning: string | null; confidence: number }
/** `actual` is null for hours not reached yet. */
export interface ForecastPoint { hour: string; actual: number | null; forecast: number }
export interface SimulationRequest { queue: string; extraAdvisors: number; from: string; to: string }
export interface SimulationResult { baselineWaitSec: number; simulatedWaitSec: number; baselineSla: number; simulatedSla: number; recommendations: string[] }
export interface CriterionScore { name: string; score: number; max: number; evidence: string; timestamp: string }
export interface QualityReview { callId: string; advisor: string; overall: number; criteria: CriterionScore[]; counterfactual: string }
export interface ComplaintCase { id: string; summary: string; severity: string; escalationRisk: number; cluster: string; hoursLeft: number }
export interface Scenario { id: string; title: string; profile: string; difficulty: string; origin: string }
export interface Opportunity { customer: string; offer: string; relevance: number; reason: string }
