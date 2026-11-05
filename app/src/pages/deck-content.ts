/**
 * The "Ideation Validation" deck as data, so the app can present and cross-check it.
 * Each idea says whether the app already demonstrates it (LIVE), partly (PARTIAL) or not yet (ROADMAP).
 */
export interface Idea {
  group: string; lines: string[]; tech: string; data: string; impact: string;
  decision: 'PRODUCTION' | 'PROTOTYPE' | 'PERSPECTIVE'; coverage: 'LIVE' | 'PARTIAL' | 'ROADMAP'; demoNote: string;
}

export interface DeckPersona {
  key: string; accent: string; initials: string; name: string; role: string; agent: string; needsRole: string; url: string;
  quote: string; topPain: string; hmw: string; techniques: string[]; ideas: Idea[]; decisionSummary: string;
}

type IdeaRow = [group: string, a: string, b: string, tech: string, data: string, impact: string,
  decision: Idea['decision'], coverage: Idea['coverage'], note: string];

const idea = ([group, a, b, tech, data, impact, decision, coverage, demoNote]: IdeaRow): Idea =>
  ({ group, lines: [a, b], tech, data, impact, decision, coverage, demoNote });

function summary(ideas: Idea[]): string {
  const n = (d: string) => ideas.filter((i) => i.decision === d).length;
  const p = n('PRODUCTION'), t = n('PROTOTYPE'), x = n('PERSPECTIVE');
  return (p > 0 ? `${p} prod` : '') + (t > 0 ? `${p > 0 ? ' · ' : ''}${t} proto` : '') + (x > 0 ? `${p + t > 0 ? ' · ' : ''}${x} persp` : '');
}

function persona(p: Omit<DeckPersona, 'ideas' | 'decisionSummary'>, rows: IdeaRow[]): DeckPersona {
  const ideas = rows.map(idea);
  return { ...p, ideas, decisionSummary: summary(ideas) };
}

export const PERSONAS: DeckPersona[] = [
  persona({ key: 'client', accent: 'p-client', initials: 'YT', name: 'Yasmine Toumi', role: 'The Client, end customer', agent: 'Client Simulator Agent',
      needsRole: 'CLIENT', url: '/client', quote: "I don't want to explain my problem five times, just fix it.", topPain: 'Repeats her story',
      hmw: 'How might we simulate clients as varied and demanding as real ones?', techniques: ['LLM personas', 'State machine', 'Memory', 'Rules', 'Scoring'] }, [
    ['Persona engine', 'Dynamic generator, persona library, persona mixing', 'Communication style and difficulty level',
      'High', 'High', 'High', 'PRODUCTION', 'LIVE', 'Pick a persona, mix a second one, set the difficulty.'],
    ['Emotional dynamics', 'Mood, patience and frustration engine', 'Customer effort simulation',
      'High', 'Medium', 'High', 'PRODUCTION', 'LIVE', 'Mood and patience move with every reply you choose.'],
    ['Context & memory', 'Historical memory of calls and promises', 'Multi-intent and repeat-contact customers',
      'Medium', 'Medium', 'High', 'PROTOTYPE', 'LIVE', "Toggle 'repeat contact' to see memory change the call."],
    ['Outcome signals', 'Churn simulator', 'Expectation simulator',
      'Medium', 'Low', 'High', 'PROTOTYPE', 'LIVE', 'Every call ends with churn risk and an expectation check.']]),
  persona({ key: 'advisor', accent: 'p-advisor', initials: 'KB', name: 'Karim Belhadj', role: 'The Customer Advisor, conseiller', agent: 'Customer Advisor Agent',
      needsRole: 'ADVISOR', url: '/advisor', quote: 'I just need the right answer in one click, not five open tabs.', topPain: 'Five tabs, one answer',
      hmw: 'How might we get advisors the right answer in one search, not five?', techniques: ['RAG', 'Intent classification', 'Agentic tool calling', 'Business rules'] }, [
    ['Understand the request', 'Intent detection', 'Multi-intent detection in one conversation',
      'High', 'High', 'High', 'PRODUCTION', 'LIVE', 'Detected intents show as chips on the customer card.'],
    ['360° customer view', 'Identification and history of the customer', 'Contract, product, billing and ticket look-ups',
      'High', 'Medium', 'High', 'PRODUCTION', 'LIVE', 'The Customer 360° card.'],
    ['Knowledge & rules', 'Knowledge search over FAQs and documentation', 'Business-rule search and live suggestions',
      'High', 'Medium', 'High', 'PRODUCTION', 'LIVE', 'Search the knowledge assistant for a sourced answer.'],
    ['Guided actions', 'Escalation and transfer recommendation', 'Plain explanations, personalized replies, policy check',
      'Medium', 'Medium', 'High', 'PROTOTYPE', 'PARTIAL', 'Policy warning and an escalate action; no transfer recommender yet.']]),
  persona({ key: 'workforce', accent: 'p-workforce', initials: 'SG', name: 'Sana Gharbi', role: 'The Workforce Manager', agent: 'Workforce Manager Agent (RL)',
      needsRole: 'WORKFORCE', url: '/workforce', quote: 'I need to see problems before they happen, not after.', topPain: 'Sees spikes too late',
      hmw: 'How might we help managers see and simulate problems before they happen?', techniques: ['Time series', 'Reinforcement learning', 'Simulation', 'KPIs'] }, [
    ['Forecast & monitor', 'Demand, workload and waiting-time prediction', 'Overload, underuse and availability monitoring',
      'High', 'Medium', 'High', 'PRODUCTION', 'LIVE', 'Forecast vs actual chart per queue.'],
    ['Routing & allocation (RL)', 'Dynamic allocation and skill-based routing', 'Queue balancing, reassignment, priorities',
      'High', 'High', 'High', 'PRODUCTION', 'PARTIAL', 'A local search moves advisors between queues, each move explained and checked by simulation; not reinforcement learning.'],
    ['Scheduling & staffing', 'Breaks, shifts and dynamic staffing', 'Peak periods, absence and overtime simulation',
      'Medium', 'Medium', 'High', 'PROTOTYPE', 'LIVE', 'The what-if simulation adds advisors in a time window.'],
    ['Risk & emergencies', 'Emergency resource allocation', 'Reputation and financial damage risk',
      'Low', 'Low', 'Medium', 'PERSPECTIVE', 'ROADMAP', 'Kept for later, as decided in the deck.']]),
  persona({ key: 'quality', accent: 'p-quality', initials: 'NC', name: 'Nour Chaabane', role: 'The Quality Analyst', agent: 'Quality Analyst Agent',
      needsRole: 'QUALITY', url: '/quality', quote: 'I can only listen to a fraction of calls, what about the rest?', topPain: 'Reviews a small sample',
      hmw: 'How might we evaluate every interaction, not just a sample of them?', techniques: ['LLM as judge', 'Speech-to-text', 'Sentiment analysis'] }, [
    ['Scoring grid', 'Accuracy, compliance, communication, resolution, satisfaction', 'Overall score with criterion-by-criterion reasons',
      'High', 'Medium', 'High', 'PRODUCTION', 'LIVE', 'Every review shows score, criteria and evidence.'],
    ['Error detection', 'Procedure violations, wrong or missing information', 'Unsupported promises, unresolved issues',
      'High', 'Medium', 'High', 'PRODUCTION', 'LIVE', 'Each lost point links to the transcript moment.'],
    ['Coaching', 'Coaching recommendations per advisor', 'Strength and weakness detection',
      'Medium', 'Medium', 'High', 'PROTOTYPE', 'LIVE', 'The coaching hint on each review.'],
    ['Quality analytics', 'Advisor history, evolution and benchmarking', 'Frequent errors and root causes',
      'Medium', 'Medium', 'Medium', 'PROTOTYPE', 'LIVE', 'Team analytics: 8-week trend per advisor, frequent errors, root causes and a coaching plan (simulated history).']]),
  persona({ key: 'training', accent: 'p-training', initials: 'RA', name: 'Rim Ayari', role: 'The Training Lead', agent: 'Training Agent',
      needsRole: 'TRAINER', url: '/training', quote: 'I want new advisors to fail safely in training, not live with a real customer.', topPain: 'Manual role-play',
      hmw: 'How might we let advisors practise any situation safely before facing it live?', techniques: ['LLM scenarios', 'Templates', 'Replay', 'What-if', 'QA links'] }, [
    ['Scenario builder', 'Automatic scenario generator (customer + problem + goal)', 'Template library and random combinations',
      'High', 'High', 'High', 'PRODUCTION', 'LIVE', 'Generate a scenario with the real generator: 15 problems, three languages, 17 complications.'],
    ['Replay & what-if', 'Scenario replay and mutation', 'What-if generator: change one parameter, compare',
      'High', 'High', 'High', 'PRODUCTION', 'LIVE', 'Replay a scenario, or make a harder or easier copy and compare; every copy keeps its parent.'],
    ['Stress & edge cases', 'Multi-event and rare-event scenarios', 'Automatic difficulty ramp',
      'Medium', 'Medium', 'High', 'PROTOTYPE', 'PARTIAL', 'Rare events and a difficulty ramp exist in the agent; the page offers harder and easier copies.'],
    ['Adaptive training', 'Training needs identified from QA weaknesses', 'Scenario recommendations per advisor',
      'Medium', 'Medium', 'High', 'PROTOTYPE', 'LIVE', 'The coach plan turns weak quality criteria of an advisor into scenarios, played in the advisor console.']]),
  persona({ key: 'complaint', accent: 'p-complaint', initials: 'AJ', name: 'Amine Jebali', role: 'The Complaint Manager', agent: 'Complaint Manager Agent',
      needsRole: 'COMPLAINT', url: '/complaints', quote: "A complaint isn't closed when it's answered, it's closed when it's resolved and trusted again.", topPain: 'Causes found case by case',
      hmw: 'How might we catch critical complaints early and fix their causes?', techniques: ['NLP', 'Classification', 'Alerts', 'Topic clustering'] }, [
    ['Triage & routing', 'Priority, severity, urgency, escalation risk', 'Automatic complaint routing',
      'High', 'Medium', 'High', 'PRODUCTION', 'LIVE', 'Cases in four severity lanes: root cause, severity and escalation risk in points, a deadline.'],
    ['Early warning', 'Critical-case detection and supervisor alerts', 'Complaint prioritization',
      'Medium', 'Medium', 'High', 'PROTOTYPE', 'LIVE', 'A banner for a case at risk or past its deadline, with Alert supervisor.'],
    ['Complaint insight', 'History, root causes, trends and hotspots', 'Complaint impact analysis',
      'Medium', 'Low', 'High', 'PROTOTYPE', 'LIVE', 'Case file, root causes and 28-day trends, deadlines met, repeat contacts (simulated history).'],
    ['Prediction & recovery', 'Escalation-path and churn-after-complaint prediction', 'Complaint recovery simulation',
      'Medium', 'Low', 'Medium', 'PERSPECTIVE', 'PARTIAL', 'Recovery is built: a follow-up call before a case closes. No learned prediction.']]),
  persona({ key: 'sales', accent: 'p-sales', initials: 'LM', name: 'Leila Mansour', role: 'The Sales Agent', agent: 'Sales Agent',
      needsRole: 'SALES', url: '/sales', quote: 'The best upsell is the one that actually solves what the client just told me.', topPain: 'Offers spotted too late',
      hmw: 'How might we suggest the right offer at the right moment, without being pushy?', techniques: ['NLP', 'Recommender system', 'Propensity models', 'LLM'] }, [
    ['Opportunity detection', 'Sales opportunity detection', 'Commercial opportunities from the conversation',
      'Medium', 'Medium', 'High', 'PROTOTYPE', 'LIVE', 'Opportunities come with the reason they were spotted.'],
    ['Offer recommendation', 'Up-selling and customer-product matching', 'Offer relevance score, personalized promotion',
      'Medium', 'Medium', 'High', 'PROTOTYPE', 'LIVE', 'Each offer carries a relevance score.'],
    ['Propensity scores', 'Purchase and churn propensity', 'Offer acceptance and rejection prediction',
      'Medium', 'Low', 'High', 'PERSPECTIVE', 'PARTIAL', 'Churn risk and the chance of a yes as readable scores, hand-weighted and counted from history, not a trained model.'],
    ['Commercial simulation', 'Revenue-per-interaction estimation', 'Commercial scenario simulation',
      'Medium', 'Low', 'Medium', 'PERSPECTIVE', 'PARTIAL', 'What an offer is worth and a replay of selling rules on a simulated history; no market model.']]),
];

/** Client journey from the deck; level 0 (low) to 4 (high) drives the emotion curve. */
export const JOURNEY = [
  { title: 'Notices an issue', text: 'Bill, service or product problem appears.', emotion: 'Neutral', level: 2 },
  { title: 'Tries self-service', text: 'Checks the app or FAQ for a quick fix.', emotion: 'Hopeful', level: 3 },
  { title: 'Waits in queue', text: 'Calls or opens chat; waits for an advisor.', emotion: 'Impatient', level: 1 },
  { title: 'Explains the issue', text: 'Repeats context, sometimes more than once.', emotion: 'Frustrated', level: 0 },
  { title: 'Gets a resolution', text: 'Advisor solves it, or escalates the ticket.', emotion: 'Relieved', level: 3 },
  { title: 'Reflects afterward', text: 'Remembers how the experience felt, not just the fix.', emotion: 'Loyal or at risk', level: 4 },
];

export const EMPATHY = [
  { title: 'Says', lines: ['I just want this fixed the first time.', 'Why do I have to repeat myself?', "Your app is fine, it's your queue that's slow."] },
  { title: 'Thinks', lines: ['Are they even reading my history?', 'I hope this advisor actually knows the product.', 'Maybe I should just switch providers.'] },
  { title: 'Does', lines: ['Tries self-service first, calls only if it fails.', 'Multitasks while on hold.', 'Repeats the issue calmly at first, then sharply.'] },
  { title: 'Feels', lines: ['Mildly anxious while waiting.', 'Frustrated by repetition, not by the issue itself.', 'Relieved and loyal when resolved quickly.'] },
];

export const BEFORE_AFTER = [
  { who: 'Client', before: 'Repeats her story after every transfer.', after: 'Understood instantly, history already known.', how: '360° view + memory' },
  { who: 'Advisor', before: 'Searches a fragmented knowledge base under pressure.', after: 'One search returns a sourced, adaptable answer.', how: 'RAG + intent detection' },
  { who: 'Workforce manager', before: 'Sees demand spikes only after they hit.', after: 'Sees the spike coming and tests the fix first.', how: 'Forecast + simulation' },
  { who: 'Quality analyst', before: 'Reviews a small sample of calls by hand.', after: 'Every call scored with evidence per point.', how: 'LLM as judge' },
];
