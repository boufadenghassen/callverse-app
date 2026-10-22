export interface CustomerContext { id: string; name: string; profile: string; intents: string[]; contract: string; openTickets: number; transfers: number; mood: string }
export interface Evidence { source: string; score: number; excerpt: string }
/** `intents` and `evidence` come from the real advisor agent; the demo data leaves them out. */
export interface SuggestedAnswer { text: string; sources: string[]; policyWarning: string | null; confidence: number; intents?: string[]; evidence?: Evidence[] }
export interface Transcript { text: string; seconds: number }
export interface SpeakRequest { text: string; role: 'advisor' | 'customer'; persona: string | null; mood: number }
export interface RoutingQueue { queue: string; name: string; calls: number; priority: number; advisors: number; recommended: number; baselineSla: number; recommendedSla: number; baselineWaitSec: number; recommendedWaitSec: number }
export interface RoutingMove { advisor: string; skills: string[]; fromQueue: string; toQueue: string; gain: number; text: string }
export interface RoutingHour { hour: string; queues: RoutingQueue[]; moves: RoutingMove[] }
/** Who should work which queue for the rest of the day. `simulated` is the independent check by a discrete-event simulation. */
export interface RoutingPlan { baselineSla: number; optimizedSla: number; moves: number; hours: RoutingHour[]; method: string; simulated?: { baselineSla: number; optimizedSla: number; replications: number } }
export interface LunchHour { hour: string; naive: number; planned: number; onDuty: number }
export interface WorstHour { hour: string; sla: number }
export interface ScheduleQueue { queue: string; name: string; advisors: number; onLunch: number; lunchHours: LunchHour[]; idealSla: number; baselineSla: number; plannedSla: number; worstBaseline: WorstHour; worstPlanned: WorstHour }
export interface Overtime { queue: string; hour: string; advisors: number; sla: number; calls: number; text: string }
/** Lunch plan for a typical day (everybody at noon against a planned spread) and the overtime still needed. */
export interface SchedulePlan { baselineSla: number; plannedSla: number; idealSla: number; queues: ScheduleQueue[]; overtime: Overtime[]; overtimeHours: number; method: string }
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
export interface CriterionScore { name: string; score: number; max: number; evidence: string; timestamp: string; good?: string[] }
export interface QualityError { rule: string; criterion: string; points: number; turn: number; timestamp: string; quote: string; reason: string; fix: string; cause: string; verdict?: 'agree' | 'disagree' | null; effect?: number; floored?: boolean }
export interface QualityStrength { turn: number; timestamp: string; text: string; rule: string; effect?: number; prevents?: string[]; why?: string }
/** One reason the overall score is what it is: `effect` is a what-if on the 0-100 score (negative = the advisor's words lowered it, positive = they protected it). */
export interface QualityDriver { turn: number; timestamp: string; rule: string; label: string; effect: number; quote: string; criterion?: string; points?: number; floored?: boolean; prevents?: string[]; why?: string }
export interface QualityCoaching { rule: string; criterion: string; tip: string; scenario: string }
export interface QualityTurn { speaker: 'advisor' | 'customer'; text: string; start: number; end: number; mood: number | null; emotion: string | null; flags: string[] }
/** The first five fields are the contract; the rest comes from the real quality agent (the demo data leaves them out). */
export interface QualityReview {
  callId: string; advisor: string; overall: number; criteria: CriterionScore[]; counterfactual: string;
  source?: string; date?: string | null; durationSec?: number; intent?: string; moodSource?: string;
  adjusted?: boolean; originalOverall?: number;
  errors?: QualityError[]; strengths?: QualityStrength[]; coaching?: QualityCoaching[]; turns?: QualityTurn[]; moodCurve?: [number, number][];
  drivers?: { hurt: QualityDriver[]; helped: QualityDriver[] };
}
export interface ErrorStat { rule: string; label: string; calls: number; share: number; cause: string }
/** A good behaviour and how often it was seen: the share of calls where it showed at least once. */
export interface StrengthStat { rule: string; label: string; calls: number; share: number; why: string }
export interface AdvisorStats {
  advisor: string; calls: number; avgOverall: number; vsTeam: number; avgByCriterion: Record<string, number>; weeks: (number | null)[]; trend: number | null;
  weakest: { criterion: string; avg: number }; strongest: { criterion: string; avg: number }; topErrors: ErrorStat[]; topStrengths?: StrengthStat[];
  coaching: { rule: string; label: string; calls: number; tip: string; scenario: string }[]; lastCalls: string[];
}
/** What the reviewer checks of the analyst's findings: `agree` = it is an error, `disagree` = it is not (and stops counting). */
export interface Agreement { judged: number; agree: number; disagree: number; rate: number | null; byRule: { rule: string; label: string; agree: number; disagree: number }[] }
export interface ReviewFilter { advisor?: string; rule?: string; below?: number }
export interface EvalRule { rule: string; label: string; tp: number; fn: number; fp: number; tn: number; judged: number; precision: number | null; recall: number | null; f1: number | null }
export interface EvalSet { split: string; cases: number; judgements: number; precision: number; recall: number; f1: number; accuracy: number; rules: EvalRule[]; mistakes: { case: string; rule: string; kind: string; text?: string }[] }
/** How accurate the quality analyst is, measured on hand-labelled calls (development and held-out test). */
export interface QualityEvaluation { semantic: boolean; dev: EvalSet; test: EvalSet; journey: string[]; limits: string }
export interface QualityAnalytics {
  agreement?: Agreement; rules?: { rule: string; label: string }[];
  team: { calls: number; avgOverall: number; avgByCriterion: Record<string, number>; weeks: (number | null)[]; topErrors: ErrorStat[]; topStrengths?: StrengthStat[];
          causes: { cause: string; calls: number; share: number }[]; byIntent: { intent: string; calls: number; avg: number }[] } | null;
  advisors: AdvisorStats[]; method: string;
}
export interface ComplaintCase { id: string; summary: string; severity: string; escalationRisk: number; cluster: string; hoursLeft: number }
export interface Scenario { id: string; title: string; profile: string; difficulty: string; origin: string }
/** One reason an offer is suggested, in points of its 0-100 relevance (the sales agent's explanation). */
export interface SalesFactor { name: string; points: number; why: string }
/** Say it now, or wait until the customer's problem is solved. */
export interface SalesTiming { cue: 'now' | 'after_resolution'; why: string }
/** The first four fields are the contract; the rest comes from the real sales agent (the demo data leaves them out). */
export interface Opportunity {
  customer: string; offer: string; relevance: number; reason: string;
  customerId?: string; offerId?: string; price?: string; kind?: string; pitch?: string; need?: { key: string; label: string };
  factors?: SalesFactor[]; timing?: SalesTiming; counterfactual?: string | null; alternatives?: { offer: string; relevance: number }[];
}
export interface SalesTurn { speaker: 'advisor' | 'customer'; text: string; start?: number; mood?: number }
/** A need the customer voiced (or their file shows), with the words that show it. */
export interface SalesSignal { need: string; label: string; quote: string; turn: number | null; time: string | null; mentions: number; strength: number; source: 'conversation' | 'file' }
export interface SalesDetection { customerId: string | null; customer: string | null; mood: number; signals: SalesSignal[]; offers: Opportunity[]; skipped: { offerId: string; offer: string; why: string }[] }
export interface SalesOutcome { customerId: string | null; offerId: string; outcome: 'accepted' | 'declined'; relevance: number; cue: string; need: string }
export interface SalesStatRow { label: string; key: string; offered: number; accepted: number; rate: number | null }
/** Which offers convert. The history is simulated until real outcomes are logged. */
export interface SalesAnalytics { total: number; accepted: number; rate: number | null; simulated: number; byOffer: SalesStatRow[]; byRelevance: SalesStatRow[]; byMoment: SalesStatRow[]; byNeed: SalesStatRow[]; method: string }
