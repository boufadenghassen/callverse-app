"""Customer simulator agent: a persona with mood and patience that answers the advisor in real time.

A faithful port of app/src/pages/client-simulator.ts and customer-llm.ts, so the web app's training page and this
service tell the same story (tests/test_customer.py checks both against the same recorded calls). The rules decide how mood,
patience and churn change; read_advisor() and customer_line() only read and write words. To use a real LLM later, replace
those two functions and keep their signatures.
"""
import math
import re
import secrets
from dataclasses import dataclass, field

MAX_MOVES = 6

# traits are 0..1 sensitivities; mood and patience start at 0..100
PERSONAS = {
    "IMPATIENT": dict(label="Impatient but fair", mood=55, patience=65, repeat=0.9, empathy=0.5, speed=0.9),
    "ANXIOUS": dict(label="Anxious first-timer", mood=50, patience=75, repeat=0.5, empathy=0.95, speed=0.4),
    "ANGRY_PREMIUM": dict(label="Angry premium client", mood=35, patience=45, repeat=1.0, empathy=0.6, speed=1.0),
    "LOYAL_AT_RISK": dict(label="Loyal but at risk", mood=60, patience=60, repeat=0.8, empathy=0.8, speed=0.6),
    "NEW_SUBSCRIBER": dict(label="New subscriber", mood=65, patience=85, repeat=0.3, empathy=0.7, speed=0.3),
}
DIFFICULTIES = {"EASY": dict(penalty=0.7, patience_shift=15), "MEDIUM": dict(penalty=1.0, patience_shift=0), "HARD": dict(penalty=1.4, patience_shift=-15)}
INTENTS = {
    "BILLING": "I was charged twice on my September bill.",
    "ROAMING": "My roaming bundle did not work abroad.",
    "CANCELLATION": "I want to cancel, and this fee makes no sense.",
}
MOVES = {
    "EMPATHY": "Acknowledge the frustration and use her history",
    "ASK_REPEAT": "Ask her to explain the problem again",
    "TRANSFER": "Transfer her to the billing team",
    "CHECK_POLICY": "Check the refund policy before promising",
    "PROMISE": "Promise the refund right away",
    "FOLLOW_UP": "Confirm the fix in writing and set a follow-up",
    "RUDE": "Raised your voice or was rude",
    "OTHER": "Said something else",
}


def js_round(x: float) -> int:
    """JavaScript's Math.round (halves go up), so mood numbers match the TypeScript version exactly."""
    return math.floor(x + 0.5)


def clamp(v: float) -> int:
    return max(0, min(100, js_round(v)))


# ---- reading the advisor: first match wins, specific actions before the polite ones that accompany them
_READERS = [
    ("TRANSFER", r"\b(transfer|put you through|pass you (on|to)|another (team|department|colleague|advisor|agent)|the (billing|technical|roaming) (team|department)|route you)\b"),
    ("ASK_REPEAT", r"\b(repeat|say (that|it) again|explain (it |that |the problem |the issue )?again|tell me (it |that |the story )?again|from the (start|beginning)|go over (it|that) again|what (was|is) (your|the) (problem|issue))\b"),
    ("PROMISE", r"\b(i promise|i guarantee|i('| wi)ll (refund|credit|reimburse|waive)|(refund|credit)(ing)? (you )?(right away|immediately|now|today)|you('| wi)ll (get|receive) (a|your|the) (full )?(refund|credit)|consider it (done|refunded)|waive the fee)\b"),
    ("CHECK_POLICY", r"\b(check|verify|confirm|review|look (up|into|at)|consult|read)\b.{0,40}\b(polic(y|ies)|procedure|rules?|approval|eligib\w+|terms|conditions|conditions)\b"),
    ("FOLLOW_UP", r"\b(in writing|written confirmation|by e-?mail|send you (an? )?(e-?mail|message|sms|confirmation)|follow(-| )?up|call you back|get back to you|reference number|ticket number|summary of)\b"),
    ("EMPATHY", r"\b(sorry|apolog\w+|i understand|understandable|i can (see|imagine|hear)|that must be|frustrat\w+|annoying|thank you for (your )?patience|thanks for (your )?patience|i hear you|appreciate)\b"),
]
READERS = [(move, re.compile(rx, re.I)) for move, rx in _READERS]


# insults, three or more words in capitals, three or more exclamation marks: she hears shouting even in a typed reply
RUDE_WORDS = re.compile(r"\b(shut up|stupid|idiot|dumb|useless|moron|bullshit|bloody|damn|crap|shit|fuck\w*|what the (hell|heck)|are you (deaf|stupid|kidding me)|nonsense)\b", re.I)
SHOUTING = re.compile(r"!{3,}|(?:\b[A-Z]{3,}\b\W+){2,}\b[A-Z]{3,}\b")


def raised_voice(tone: dict | None) -> bool:
    """The emotion model heard anger or disgust in a voice note, and the mood it computes is low."""
    return bool(tone) and tone["emotion"] in ("anger", "disgust") and tone["mood"] <= 30


def read_advisor(text: str, tone: dict | None = None) -> str:
    if raised_voice(tone) or RUDE_WORDS.search(text) or SHOUTING.search(text):
        return "RUDE"
    return next((move for move, rx in READERS if rx.search(text)), "OTHER")


# ---- the customer's words, by mood band: 0 = upset, 1 = unsure, 2 = content
LINES = {
    "EMPATHY": [
        ["Fine, but words don't fix my bill.", "That's nice. Now what are you actually going to do?", "Sorry doesn't give me my money back.", "I've heard that before. Show me, don't tell me."],
        ["Okay. At least you seem to know my file.", "Thanks, I appreciate you saying that.", "Alright, that helps a little. Go on.", "Okay, I'm listening."],
        ["Thank you, that already feels better.", "That's kind of you, thank you. I feel heard.", "Thanks, honestly that means a lot.", "I appreciate that. Let's sort it out together."],
    ],
    "ASK_REPEAT": [
        ["Again?! I already told your colleagues everything!", "Seriously? This is the third person I explain this to.", "No. I'm not going through it all again.", "You have my file. Read it!"],
        ["Sure... though I did explain this before.", "Do I really have to? Fine, from the start then.", "Okay, but it's frustrating to repeat myself.", "I'll say it once more, then please write it down."],
        ["Of course, let me go through it.", "No problem, here's what happened.", "Sure, I'll explain it from the beginning.", "Happy to. It started on the first of the month."],
    ],
    "TRANSFER": [
        ["Another transfer? Unbelievable.", "No! Every transfer means starting from zero. Don't you dare.", "That's the whole problem with your company.", "Transfer me again and I cancel."],
        ["Please don't make me start over with someone new.", "Will they know what I told you? Please make sure they do.", "Hmm. Okay, but stay on the line until they pick up.", "I'd rather you handled it, but fine."],
        ["Alright, I'll hold.", "Okay, thank you for putting me through.", "Sure, I'll wait.", "No problem, if they can fix it."],
    ],
    "CHECK_POLICY": [
        ["How long is this going to take?", "I don't have all day. Is this going to be quick?", "Checking, checking... it's always checking with you people.", "Hurry up, please. I've waited long enough."],
        ["Okay, I'll wait a moment.", "Fine, take your time but don't forget me.", "Alright, as long as it gets sorted.", "Okay. Let me know what you find."],
        ["Good, I'd rather it be right.", "Thank you for being careful about it.", "Sure, take the time you need.", "That makes sense. Better to be sure."],
    ],
    "PROMISE": [
        ["I'll believe it when I see it.", "You people always promise. Put it in writing.", "Last time they said that, nothing happened.", "Okay... but I've heard that before."],
        ["Good. I hope that's really confirmed.", "Okay, thank you. Is that definitely approved?", "That would be great, if it's really going to happen.", "Alright. When will I see it?"],
        ["Wonderful, thank you!", "That's great news, thank you so much.", "Perfect, that is exactly what I wanted.", "Brilliant. I really appreciate it."],
    ],
    "FOLLOW_UP": [
        ["Fine. I'll check my email.", "Okay. But if nothing arrives, I'm calling again.", "Send it. I'll be watching.", "Fine. Do not forget this time."],
        ["Okay, that works for me.", "Alright, thank you. I will look out for it.", "Good, I'd like to have that in writing.", "Okay. Thanks for following through."],
        ["Perfect. That's all I needed.", "Great, thank you. You have been very helpful.", "Wonderful, that's exactly what I hoped for.", "Thank you, I'm glad we sorted this out."],
    ],
    "RUDE": [
        ["Don't shout at me! I'm the one with the problem.", "How dare you speak to me like that?", "I want to speak to your supervisor. Right now.", "That tone is unacceptable."],
        ["Excuse me? There's no need to raise your voice.", "Was that really necessary? I only want this fixed.", "I would like you to speak to me politely, please."],
        ["Oh... did I say something wrong? You sound upset.", "Sorry, I did not mean to annoy you. Is everything alright?", "Um, okay. Is there a problem?"],
    ],
    "OTHER": [
        ["I'm not sure what that means for my problem.", "Okay... and? What are you going to do about it?", "That doesn't answer my question."],
        ["Hm, okay. And then?", "I'm not sure I follow. Can you be more specific?", "Alright... go on."],
        ["Okay, sure.", "Alright, I see. Please continue.", "Mm-hm, go ahead."],
    ],
}
FLAVOUR = {
    "IMPATIENT": [" I have somewhere to be.", " Can we speed this up?", ""],
    "ANXIOUS": [" I'm sorry, I'm just really worried about this.", " I hope I'm explaining this properly.", " Thank you for being patient with me."],
    "ANGRY_PREMIUM": [" I pay a premium price for better than this.", " I expect proper service.", ""],
    "LOYAL_AT_RISK": [" I have been with you for six years, you know.", " I would hate to leave after all this time.", " This is why I stayed with you."],
    "NEW_SUBSCRIBER": [" I'm still new, I don't know how any of this works.", " Sorry, I am still learning how it all works.", ""],
}
# when the advisor says something that matches no move she still answers what was said: an amount, a greeting or a question
TOPIC = {"BILLING": "my bill", "ROAMING": "my roaming bundle", "CANCELLATION": "my cancellation"}
AMOUNT = re.compile(r"[$€£]\s?\d[\d,.]*|\b\d[\d,.]*\s?(?:tnd|dinars?|dollars?|euros?|usd|eur)\b", re.I)
GREETING = re.compile(r"^\W*(hello|hi|hey|good (morning|afternoon|evening))\b", re.I)
QUESTION = re.compile(r"\?|^\s*(what|why|how|when|where|who|which|do|does|did|are|is|can|could|would|will)\b", re.I)
REACTIONS = {
    "amount": [
        ["Why are you talking about {a}? That is not what I called about.", "{a}? Where did that come from? Read my file properly!"],
        ["Sorry, {a}? I don't think that is the amount I'm asking about.", "Hm, {a}... that does not match what I see. Can you check?"],
        ["Sorry, did you say {a}? I may have misunderstood, could you explain?", "Oh, {a}? I was not expecting that figure, can you tell me more?"],
    ],
    "greeting": [
        ["Yes, hello. Can we get to {t} now?", "Hello. I have been waiting, can we talk about {t}?"],
        ["Hello. So, about {t}?", "Hi. Can you help me with {t}?"],
        ["Hello! Thank you for taking my call. It is about {t}.", "Hi there. I am calling about {t}."],
    ],
    "question": [
        ["Why are you asking me that? I called about {t}.", "That is not an answer. I am calling about {t}!"],
        ["Hm, I'm not sure how to answer that. Is it about {t}?", "I'm not sure what you mean. Can we go back to {t}?"],
        ["Sure, I can try to answer. Is it about {t}?", "Of course. Just so we're on the same page, this is about {t}."],
    ],
}


def reaction(intent: str, move: str, band: int, advisor_said: str | None) -> list[str] | None:
    """The lines that answer what the advisor actually said, or None when it was nothing she can react to."""
    if move != "OTHER" or not advisor_said:
        return None
    m = AMOUNT.search(advisor_said)
    kind = "amount" if m else "greeting" if GREETING.search(advisor_said) and len(advisor_said.split()) <= 8 else "question" if QUESTION.search(advisor_said) else None
    if not kind:
        return None
    return [line.replace("{a}", m.group(0).strip() if m else "").replace("{t}", TOPIC[intent]) for line in REACTIONS[kind][band]]


HANG_UP = ["That's it. I'm done, goodbye.", "I've had enough. Goodbye.", "This is pointless. I am hanging up."]


def _unit(ch: str) -> int:
    """charCodeAt(0): the first UTF-16 unit of the character."""
    c = ord(ch)
    return c if c < 0x10000 else 0xD800 + ((c - 0x10000) >> 10)


def pick_index(seed: str, n: int) -> int:
    """Same inputs always give the same line, so a call replays identically (FNV-1a, as in the TypeScript version)."""
    h = 2166136261
    for ch in seed:
        h = ((h ^ _unit(ch)) * 16777619) & 0xFFFFFFFF
    return h % n


def customer_line(persona: str, intent: str, move: str, mood: int, memory: bool, hung_up: bool, turn: int, advisor_said: str | None) -> str:
    seed = f"{persona}|{intent}|{move}|{turn}|{advisor_said or ''}"
    if hung_up:
        return HANG_UP[pick_index(seed, len(HANG_UP))]
    band = 0 if mood < 30 else 1 if mood < 60 else 2
    options = reaction(intent, move, band, advisor_said) or list(LINES[move][band])
    if move == "ASK_REPEAT" and memory and band < 2:
        options.append("You have my history right there. This is the third time I call about it.")
    line = options[pick_index(seed, len(options))]
    flavour = FLAVOUR[persona][band]
    if flavour and pick_index(seed + "|f", 3) != 0:
        line += flavour
    return line


# ---- the call, replayed from the moves so far
@dataclass
class Turn:
    move: str
    said: str | None
    client: str
    mood: int
    patience: int


@dataclass
class Replay:
    opening: str
    turns: list[Turn]
    mood: int
    patience: int
    outcome: dict | None


def replay(persona: str, mix: str | None, difficulty: str, intent: str, memory: bool, moves: list[str], said: list[str | None]) -> Replay:
    p, d = PERSONAS[persona], DIFFICULTIES[difficulty]
    repeat, empathy, speed, mood, patience = p["repeat"], p["empathy"], p["speed"], p["mood"], p["patience"]
    if mix:  # persona mixing: blend the two profiles
        q = PERSONAS[mix]
        repeat, empathy, speed = (repeat + q["repeat"]) / 2, (empathy + q["empathy"]) / 2, (speed + q["speed"]) / 2
        mood, patience = math.trunc((mood + q["mood"]) / 2), math.trunc((patience + q["patience"]) / 2)
    mood = clamp(mood)
    patience = clamp(patience + d["patience_shift"])

    opening = INTENTS[intent] + (" This is the third time I call about it." if memory else "")
    turns: list[Turn] = []
    effort, checked, risky, rude, closed, hung_up = 0, False, False, False, False, False
    neg = d["penalty"]

    for i, m in enumerate(moves):
        if len(turns) >= MAX_MOVES or closed or hung_up:
            break
        if m == "EMPATHY":
            dm, dp = (10 + 14 * empathy if memory else 4 + 8 * empathy), 4
        elif m == "ASK_REPEAT":
            dm, dp = -(8 + 10 * repeat) * neg * (1.3 if memory else 1), -(10 + 12 * repeat) * neg
            effort += 1
        elif m == "TRANSFER":
            dm, dp = -8 * neg, -(8 + 10 * speed) * neg
            effort += 1
        elif m == "CHECK_POLICY":
            dm, dp, checked = 2, -(4 + 6 * speed) * neg, True
        elif m == "PROMISE":
            dm, dp = 14, 5
            if not checked:
                risky = True
        elif m == "RUDE":
            dm, dp, rude = -18 * neg, -(18 + 8 * speed) * neg, True
        elif m == "OTHER":
            dm, dp = 1, -3
        else:  # FOLLOW_UP
            dm, dp, closed = 8 + 6 * empathy, 6, True
        mood = clamp(mood + dm)
        patience = clamp(patience + dp)
        if patience <= 0:
            hung_up = True
        advisor_said = said[i] if i < len(said) else None
        turns.append(Turn(m, advisor_said, customer_line(persona, intent, m, mood, memory, hung_up, i, advisor_said), mood, patience))

    outcome = None
    if hung_up or closed or len(turns) >= MAX_MOVES:
        met = closed and not risky and not rude and not hung_up and mood >= 55
        churn = clamp(100 - mood * 0.55 - patience * 0.35 + effort * 7 + (12 if risky else 0) + (10 if rude else 0) + (25 if hung_up else 0))
        notes = []
        if effort > 0:
            notes.append(f"Customer effort: the client had to repeat or be transferred {effort} time(s).")
        if risky:
            notes.append("Compliance risk: a refund was promised before the policy was checked.")
        if rude:
            notes.append("Conduct: the advisor raised their voice or was rude to the client.")
        if memory and "ASK_REPEAT" in moves:
            notes.append("Memory ignored: the history was on file but the client was asked to repeat.")
        if not closed and not hung_up:
            notes.append("The call ended without a written follow-up.")
        verdict = ("The client hung up." if hung_up else "Resolved: the client leaves satisfied." if met
                   else "Closed, but trust is shaky." if closed else "Call left open.")
        outcome = dict(verdict=verdict, expectationMet=met, churnRisk=churn, effort=effort, notes=notes)
    return Replay(opening, turns, mood, patience, outcome)


# ---- live sessions (in memory: restart the service and open calls are gone)
@dataclass
class Session:
    persona: str
    mix: str | None
    difficulty: str
    intent: str
    memory: bool
    moves: list[str] = field(default_factory=list)
    said: list[str | None] = field(default_factory=list)


SESSIONS: dict[str, Session] = {}
MAX_SESSIONS = 200  # ponytail: oldest call is dropped past this; a database if calls must survive restarts


def start(persona: str, mix: str | None, difficulty: str, intent: str, memory: bool) -> dict:
    if len(SESSIONS) >= MAX_SESSIONS:
        SESSIONS.pop(next(iter(SESSIONS)))
    sid = secrets.token_hex(8)
    SESSIONS[sid] = Session(persona, mix, difficulty, intent, memory)
    r = replay(persona, mix, difficulty, intent, memory, [], [])
    return dict(id=sid, persona=PERSONAS[persona]["label"], opening=r.opening, mood=r.mood, patience=r.patience)


def say(sid: str, text: str, tone: dict | None = None) -> dict:
    s = SESSIONS[sid]  # KeyError = unknown call, the API turns it into 404
    before = replay(s.persona, s.mix, s.difficulty, s.intent, s.memory, s.moves, s.said)
    if before.outcome is not None:
        return dict(ended=True, outcome=before.outcome, mood=before.mood, patience=before.patience, client=None, move=None, moveLabel=None)
    move = read_advisor(text, tone)
    s.moves.append(move)
    s.said.append(text)
    r = replay(s.persona, s.mix, s.difficulty, s.intent, s.memory, s.moves, s.said)
    t = r.turns[-1]
    return dict(ended=r.outcome is not None, outcome=r.outcome, mood=t.mood, patience=t.patience, client=t.client, move=move, moveLabel=MOVES[move])


def transcript(sid: str) -> tuple[list[dict], dict | None, str]:
    """The call so far as turns for the quality analyst (times are estimated by the analyst), its outcome so far, and the customer persona."""
    s = SESSIONS[sid]  # KeyError = unknown call
    start = replay(s.persona, s.mix, s.difficulty, s.intent, s.memory, [], [])
    run = replay(s.persona, s.mix, s.difficulty, s.intent, s.memory, s.moves, s.said)
    turns = [dict(speaker="customer", text=start.opening, mood=start.mood)]
    for i, t in enumerate(run.turns):
        turns += [dict(speaker="advisor", text=s.said[i]), dict(speaker="customer", text=t.client, mood=t.mood)]
    return turns, run.outcome, s.persona
