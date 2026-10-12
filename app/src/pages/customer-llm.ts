import type { DifficultyKey, IntentKey, MoveKey, PersonaKey } from './client-simulator';

/**
 * The two language skills of the simulated customer, as plain functions:
 *   readAdvisor: what did the advisor just do?   (text -> one of the simulator's moves)
 *   customerLine: what does the customer say back? (state -> a sentence)
 * Both are rule-based stand-ins so the demo works offline and stays testable. The rules in client-simulator.ts still
 * decide how mood, patience and churn change; these functions only read and write words. To use a real LLM later, replace
 * the bodies (they will become async, and replay() with them) and keep the signatures.
 */

// ---- reading the advisor ------------------------------------------------------------------------------
// First match wins, so more specific actions come before the polite ones that often accompany them.
const READERS: [MoveKey, RegExp][] = [
  ['TRANSFER', /\b(transfer|put you through|pass you (on|to)|another (team|department|colleague|advisor|agent)|the (billing|technical|roaming) (team|department)|route you)\b/i],
  ['ASK_REPEAT', /\b(repeat|say (that|it) again|explain (it |that |the problem |the issue )?again|tell me (it |that |the story )?again|from the (start|beginning)|go over (it|that) again|what (was|is) (your|the) (problem|issue))\b/i],
  ['PROMISE', /\b(i promise|i guarantee|i('| wi)ll (refund|credit|reimburse|waive)|(refund|credit)(ing)? (you )?(right away|immediately|now|today)|you('| wi)ll (get|receive) (a|your|the) (full )?(refund|credit)|consider it (done|refunded)|waive the fee)\b/i],
  ['CHECK_POLICY', /\b(check|verify|confirm|review|look (up|into|at)|consult|read)\b.{0,40}\b(polic(y|ies)|procedure|rules?|approval|eligib\w+|terms|conditions|conditions)\b/i],
  ['FOLLOW_UP', /\b(in writing|written confirmation|by e-?mail|send you (an? )?(e-?mail|message|sms|confirmation)|follow(-| )?up|call you back|get back to you|reference number|ticket number|summary of)\b/i],
  ['EMPATHY', /\b(sorry|apolog\w+|i understand|understandable|i can (see|imagine|hear)|that must be|frustrat\w+|annoying|thank you for (your )?patience|thanks for (your )?patience|i hear you|appreciate)\b/i],
];

/** Turns what the advisor typed into the simulator move it most resembles; OTHER when it matches none. */
export function readAdvisor(text: string): MoveKey {
  return READERS.find(([, re]) => re.test(text))?.[0] ?? 'OTHER';
}

// ---- the customer's words -----------------------------------------------------------------------------
type Band = 0 | 1 | 2; // 0 = upset, 1 = unsure, 2 = content (from her current mood)
const LINES: Record<MoveKey, [string[], string[], string[]]> = {
  EMPATHY: [
    ["Fine, but words don't fix my bill.", "That's nice. Now what are you actually going to do?", "Sorry doesn't give me my money back.", "I've heard that before. Show me, don't tell me."],
    ['Okay. At least you seem to know my file.', 'Thanks, I appreciate you saying that.', 'Alright, that helps a little. Go on.', "Okay, I'm listening."],
    ['Thank you, that already feels better.', "That's kind of you, thank you. I feel heard.", 'Thanks, honestly that means a lot.', "I appreciate that. Let's sort it out together."],
  ],
  ASK_REPEAT: [
    ['Again?! I already told your colleagues everything!', 'Seriously? This is the third person I explain this to.', "No. I'm not going through it all again.", 'You have my file. Read it!'],
    ['Sure... though I did explain this before.', 'Do I really have to? Fine, from the start then.', "Okay, but it's frustrating to repeat myself.", "I'll say it once more, then please write it down."],
    ['Of course, let me go through it.', "No problem, here's what happened.", "Sure, I'll explain it from the beginning.", "Happy to. It started on the first of the month."],
  ],
  TRANSFER: [
    ['Another transfer? Unbelievable.', "No! Every transfer means starting from zero. Don't you dare.", "That's the whole problem with your company.", 'Transfer me again and I cancel.'],
    ["Please don't make me start over with someone new.", 'Will they know what I told you? Please make sure they do.', 'Hmm. Okay, but stay on the line until they pick up.', "I'd rather you handled it, but fine."],
    ["Alright, I'll hold.", 'Okay, thank you for putting me through.', "Sure, I'll wait.", 'No problem, if they can fix it.'],
  ],
  CHECK_POLICY: [
    ['How long is this going to take?', "I don't have all day. Is this going to be quick?", "Checking, checking... it's always checking with you people.", "Hurry up, please. I've waited long enough."],
    ["Okay, I'll wait a moment.", "Fine, take your time but don't forget me.", 'Alright, as long as it gets sorted.', 'Okay. Let me know what you find.'],
    ["Good, I'd rather it be right.", 'Thank you for being careful about it.', 'Sure, take the time you need.', 'That makes sense. Better to be sure.'],
  ],
  PROMISE: [
    ["I'll believe it when I see it.", "You people always promise. Put it in writing.", 'Last time they said that, nothing happened.', "Okay... but I've heard that before."],
    ["Good. I hope that's really confirmed.", "Okay, thank you. Is that definitely approved?", "That would be great, if it's really going to happen.", 'Alright. When will I see it?'],
    ['Wonderful, thank you!', "That's great news, thank you so much.", 'Perfect, that is exactly what I wanted.', 'Brilliant. I really appreciate it.'],
  ],
  FOLLOW_UP: [
    ["Fine. I'll check my email.", "Okay. But if nothing arrives, I'm calling again.", "Send it. I'll be watching.", 'Fine. Do not forget this time.'],
    ['Okay, that works for me.', 'Alright, thank you. I will look out for it.', "Good, I'd like to have that in writing.", 'Okay. Thanks for following through.'],
    ["Perfect. That's all I needed.", 'Great, thank you. You have been very helpful.', "Wonderful, that's exactly what I hoped for.", "Thank you, I'm glad we sorted this out."],
  ],
  OTHER: [
    ["I'm not sure what that means for my problem.", "Okay... and? What are you going to do about it?", "That doesn't answer my question."],
    ["Hm, okay. And then?", "I'm not sure I follow. Can you be more specific?", "Alright... go on."],
    ['Okay, sure.', 'Alright, I see. Please continue.', 'Mm-hm, go ahead.'],
  ],
};

/** A little character on top of the line, so the five personas do not all sound alike. */
const FLAVOUR: Record<PersonaKey, [string, string, string]> = {
  IMPATIENT: [' I have somewhere to be.', ' Can we speed this up?', ''],
  ANXIOUS: [" I'm sorry, I'm just really worried about this.", " I hope I'm explaining this properly.", ' Thank you for being patient with me.'],
  ANGRY_PREMIUM: [' I pay a premium price for better than this.', ' I expect proper service.', ''],
  LOYAL_AT_RISK: [' I have been with you for six years, you know.', ' I would hate to leave after all this time.', ' This is why I stayed with you.'],
  NEW_SUBSCRIBER: [" I'm still new, I don't know how any of this works.", ' Sorry, I am still learning how it all works.', ''],
};

const HANG_UP = ["That's it. I'm done, goodbye.", "I've had enough. Goodbye.", 'This is pointless. I am hanging up.'];

/** Same inputs always give the same line (the call must replay identically from its URL). */
function pickIndex(seed: string, n: number): number {
  let h = 2166136261;
  for (const ch of seed) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return (h >>> 0) % n;
}

export interface LineContext {
  persona: PersonaKey; intent: IntentKey; difficulty: DifficultyKey; move: MoveKey;
  mood: number; memory: boolean; hungUp: boolean; turn: number; advisorSaid: string | null;
}

export function customerLine(c: LineContext): string {
  const seed = `${c.persona}|${c.intent}|${c.move}|${c.turn}|${c.advisorSaid ?? ''}`;
  if (c.hungUp) return HANG_UP[pickIndex(seed, HANG_UP.length)];
  const band: Band = c.mood < 30 ? 0 : c.mood < 60 ? 1 : 2;
  const options = [...LINES[c.move][band]];
  // a repeat contact who is asked to repeat herself has something specific to say
  if (c.move === 'ASK_REPEAT' && c.memory && band < 2) options.push('You have my history right there. This is the third time I call about it.');
  let line = options[pickIndex(seed, options.length)];
  const flavour = FLAVOUR[c.persona][band];
  if (flavour && pickIndex(seed + '|f', 3) !== 0) line += flavour;
  return line;
}
