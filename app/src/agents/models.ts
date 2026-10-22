export interface CustomerContext { id: string; name: string; profile: string; intents: string[]; contract: string; openTickets: number; transfers: number; mood: string }
export interface Evidence { source: string; score: number; excerpt: string }
/** `intents` and `evidence` come from the real advisor agent; the demo data leaves them out. */
export interface SuggestedAnswer { text: string; sources: string[]; policyWarning: string | null; confidence: number; intents?: string[]; evidence?: Evidence[] }
export interface Transcript { text: string; seconds: number }
/** What the advisor agent says by itself at one point of a call: one step of its routine (acknowledge, check the policy, give the solution, confirm in writing), or a rushed advisor for demonstrations. */
export interface AutoReply { text: string; step: string; turn: number; last: boolean; sources: string[]; intents: string[]; policyWarning: string | null; style: 'careful' | 'rushed' }
/** How the advisor's voice sounded (the emotion model on a voice note): one of anger, disgust, fear, happy, neutral, sad and a 0-100 mood. */
export interface Tone { emotion: string; mood: number }
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
export interface ComplaintAction { action: string; why: string; who: string }
export interface ComplaintDeadline { slaHours: number; ageHours: number; hoursLeft: number; used: number; overdue: boolean }
export interface ComplaintWarning { why: string; hoursLeft: number; alerted: boolean }
/** The first six fields are the contract; the rest comes from the real complaint agent (the demo data leaves them out). Severity and risk come with their reasons in points. */
export interface ComplaintCase {
  id: string; summary: string; severity: string; escalationRisk: number; cluster: string; hoursLeft: number;
  clusterKey?: string; otherClusters?: string[]; cause?: string; team?: string; customerId?: string | null; customer?: string | null;
  status?: 'open' | 'taken' | 'resolved' | 'closed'; assigned?: string | null; channel?: string; source?: string; opened?: string;
  severityScore?: number; computedLevel?: string; overridden?: boolean; severityFactors?: SalesFactor[]; riskFactors?: SalesFactor[];
  deadline?: ComplaintDeadline; contacts?: number; amount?: number | null; warning?: ComplaintWarning | null; actions?: ComplaintAction[];
}
export interface ComplaintEvent { at: string; who: string; kind: string; note: string }
export interface ComplaintDetail extends ComplaintCase {
  text: string; events: ComplaintEvent[]; earlier: { id: string; summary: string; opened: string; status: string }[];
  similar: { id: string; summary: string; resolution: string }[]; worked: { code: string; label: string; count: number; of: number } | null;
  resolution: string | null; trusted: number | null; callId: string | null;
  customerFile: { id: string; name: string; profile: string; contract: string; openTickets: number; transfers: number; mood: string; tenureYears?: number; monthlyTnd?: number; usageTrend?: number } | null;
}
export interface ComplaintFollowUp { id: string; summary: string; customer: string | null; resolution: string; due: string; dueInHours: number }
/** A call the quality analyst scored where the customer hung up, left upset or nothing was agreed, with how the complaint agent would read it. */
export interface ComplaintCandidate { callId: string; advisor: string; overall: number; why: string[]; text: string; triage: ComplaintCase }
export interface ComplaintClusterStat { key: string; label: string; cause: string; open: number; last28: number; previous28: number; trend: number; avgHours: number | null; worked: { label: string; count: number; of: number } | null }
export interface ComplaintInsights {
  open: number; byLevel: Record<string, number>; avgRisk: number; overdue: number; warnings: number; followUps: number; resolved: number; avgResolutionHours: number | null;
  slaMetRate: number | null; trustRate: number | null; reopened: number; repeatRate: number | null; weeks: number[]; clusters: ComplaintClusterStat[];
  causes: { cause: string; cases: number; share: number }[]; simulated: number; method: string;
}
export interface ComplaintAct { action: 'take' | 'escalate' | 'severity' | 'alert' | 'resolve' | 'close' | 'reopen'; by: string; note?: string; resolution?: string; level?: string; trusted?: boolean }
export interface Scenario { id: string; title: string; profile: string; difficulty: string; origin: string }
export interface ScenarioDetail extends Scenario {
  customer_card?: string; trainer_brief?: string; complications?: string[]; success_criteria?: string[];
  kind?: string;
  parent_id?: string | null;
  mutation_log?: string[];
  spec?: { segment: string; difficulty: number; intent?: string; events?: string[]; language?: string };
  opening_emotion?: string; skills?: string[];
}
export interface TrainingWeakness { criterion: string; score: number }
export interface TrainingPlan {
  advisor_id: string;
  needs_training: boolean;
  focus: { skill: string; gap: number; criteria: string[] }[];
  scenarios: Scenario[];
  rationale: string[];
}
/** One reason an offer is suggested, in points of its 0-100 relevance (the sales agent's explanation). */
export interface SalesFactor { name: string; points: number; why: string }
/** Say it now, or wait until the customer's problem is solved. */
export interface SalesTiming { cue: 'now' | 'after_resolution'; why: string }
/** The first four fields are the contract; the rest comes from the real sales agent (the demo data leaves them out). */
export interface Opportunity {
  customer: string; offer: string; relevance: number; reason: string;
  customerId?: string; offerId?: string; price?: string; kind?: string; pitch?: string; need?: { key: string; label: string };
  factors?: SalesFactor[]; timing?: SalesTiming; counterfactual?: string | null; alternatives?: { offer: string; relevance: number }[];
  acceptance?: SalesAcceptance | null; expected?: SalesExpected; churn?: SalesChurn;
}
/** Risk (0-100) that the customer leaves, as a sum of named factors. */
export interface SalesChurn { score: number; level: 'Low' | 'Medium' | 'High'; factors: SalesFactor[] }
/** Chance of a yes, from what happened to similar offers in the history (null when there is no history yet). */
export interface SalesAcceptance { probability: number; similar: number; similarAccepted: number; basis: string }
/** What a yes is worth over twelve months (TND, revenue) and the expected value (chance x worth). */
export interface SalesExpected { ifYes: number; chance: number | null; tnd: number | null; how: string }
export interface SalesTurn { speaker: 'advisor' | 'customer'; text: string; start?: number; mood?: number }
/** A need the customer voiced (or their file shows), with the words that show it. */
export interface SalesSignal { need: string; label: string; quote: string; turn: number | null; time: string | null; mentions: number; strength: number; source: 'conversation' | 'file' }
export interface SalesDetection { customerId: string | null; customer: string | null; mood: number; churn?: SalesChurn; signals: SalesSignal[]; offers: Opportunity[]; skipped: { offerId: string; offer: string; why: string }[] }
export interface SalesOutcome { customerId: string | null; offerId: string; outcome: 'accepted' | 'declined'; relevance: number; cue: string; need: string }
export interface SalesStatRow { label: string; key: string; offered: number; accepted: number; rate: number | null }
/** Which offers convert. The history is simulated until real outcomes are logged. */
/** A selling rule to replay on the history: how many calls, the share with a chance to offer, the lowest relevance to offer at, only at a good moment. */
export interface SalesSimulationRequest { calls: number; share: number; minRelevance: number; goodMomentOnly: boolean }
export interface SalesPolicy { label: string; minRelevance: number; goodMomentOnly: boolean; offers: number; accepted: number; declined: number; rate: number | null; revenue: number; perCall: number }
export interface SalesSimulation { calls: number; share: number; opportunities: number; simulated: number; history: number; policies: SalesPolicy[]; yours: SalesPolicy; method: string }
export interface SalesAnalytics { total: number; accepted: number; rate: number | null; simulated: number; byOffer: SalesStatRow[]; byRelevance: SalesStatRow[]; byMoment: SalesStatRow[]; byNeed: SalesStatRow[]; method: string }
