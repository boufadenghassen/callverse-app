"""A simulated history of past calls for the quality analytics.

Six advisors with different habits talk to the customer simulator (customer.py) over the last eight weeks. What the advisors say is written
from phrase banks; what the customer answers, and her mood, come from the simulator's rules; and every call is then scored by the real
quality.review() exactly like a call from a customer. So the analytics are computed, not typed in, but the input is SIMULATED, not real.
Deterministic: the same history every time the store is empty.
"""
import datetime as dt
import random

import advisor as kb
import customer
import quality
import quality_store

GREET = ["Hello, thank you for calling, how can I help you today?", "Good afternoon, you are speaking with {name}. How can I help?", "Welcome, my name is {name}. What can I do for you?"]
IDENT = ["Before I look at the account, can you confirm your date of birth so I can verify your identity?", "Could you please confirm your full name and date of birth to verify your identity?"]
EMPATHY = ["I'm sorry about that, I understand how frustrating this must be.", "I can see why you are upset, and I apologise for the inconvenience.", "I understand, that is annoying, thank you for your patience."]
ASK_REPEAT = ["Could you explain the problem again from the start?", "Can you tell me the story again, please?"]
TRANSFER = ["Let me transfer you to the billing team.", "I will put you through to another colleague in the roaming department."]
TRANSFER_HISTORY = ["I will transfer you to the billing team, stay on the line and I will pass them your full history."]
CHECK = ["Let me check the refund policy and the approval before I promise anything.", "I will verify the eligibility rules for this first."]
PROMISE_PLAIN = ["I will refund you {amt} TND right away.", "Consider it done, I will refund the duplicate today.", "I promise you will get the refund immediately."]
PROMISE_APPROVAL = ["I will refund {amt} TND once my supervisor has approved it."]
FOLLOW = ["I will send you a confirmation by email with a reference number, and I will call you back to check.", "You will get a written confirmation by email today, with your ticket number."]
CLOSE = " Is there anything else I can help you with?"
JARGON = " The APN settings and the provisioning look fine."
WRONG = {   # a plausible mistake per topic: the knowledge base says otherwise
    "BILLING": ["I have opened the refund and it will be in your account today.", "We will answer your dispute within two days."],
    "ROAMING": ["I will reactivate the roaming bundle and the service will be restored within two days."],
    "CANCELLATION": ["I can change your plan and the change takes effect immediately."],
}
NAMES = {"Karim B.": "Karim", "Hela M.": "Hela", "Sami R.": "Sami", "Rania K.": "Rania", "Mehdi T.": "Mehdi", "Ines F.": "Ines"}

# habits: probabilities of doing each thing; drift > 0 means the advisor improved over the eight weeks, < 0 that they got worse
PROFILES = {
    "Karim B.": dict(greet=.9, ident=.65, empathy=.7, wrong=.12, jargon=.10, repeat=.15, transfer=.15, promise=.35, check=.60, approval=.5, follow=.70, close=.70, drift=0.0),
    "Hela M.": dict(greet=.95, ident=.90, empathy=.9, wrong=.04, jargon=.04, repeat=.04, transfer=.08, promise=.30, check=.95, approval=.9, follow=.92, close=.90, drift=0.0),
    "Sami R.": dict(greet=.85, ident=.60, empathy=.6, wrong=.20, jargon=.15, repeat=.20, transfer=.20, promise=.40, check=.55, approval=.5, follow=.60, close=.60, drift=0.35),
    "Rania K.": dict(greet=.80, ident=.35, empathy=.5, wrong=.15, jargon=.10, repeat=.20, transfer=.25, promise=.50, check=.35, approval=.3, follow=.55, close=.50, drift=0.0),
    "Mehdi T.": dict(greet=.90, ident=.80, empathy=.8, wrong=.10, jargon=.08, repeat=.10, transfer=.10, promise=.30, check=.80, approval=.8, follow=.80, close=.80, drift=-0.4),
    "Ines F.": dict(greet=.95, ident=.80, empathy=.95, wrong=.45, jargon=.35, repeat=.10, transfer=.10, promise=.30, check=.80, approval=.8, follow=.85, close=.90, drift=0.0),
}
GOOD = ("greet", "ident", "empathy", "check", "approval", "follow", "close")     # more of these is better; for the others (wrong, jargon, repeat, transfer, promise) less is
CALLS_PER_ADVISOR = 14
WEEKS = 8


def _p(profile: dict, key: str, age: float) -> float:
    d = profile["drift"] * (0.5 - age)                       # age 0 = today, 1 = eight weeks ago
    return max(0.02, min(0.98, profile[key] + (d if key in GOOD else -d)))


def _script(rng: random.Random, name: str, profile: dict, intent: str, age: float) -> tuple[str | None, list[str]]:
    p = lambda k: rng.random() < _p(profile, k, age)
    greet = rng.choice(GREET).format(name=NAMES[name]) if p("greet") else None
    texts: list[str] = []
    opener = ""
    if p("empathy"):
        opener = rng.choice(EMPATHY)
    if p("ident"):
        opener = (opener + " " if opener else "") + rng.choice(IDENT)
    if opener:
        texts.append(opener)
    content = kb.suggest(customer.INTENTS[intent])["text"]
    if p("wrong"):
        content = rng.choice(WRONG[intent])
    if p("jargon"):
        content += JARGON
    texts.append(content)
    if p("repeat"):
        texts.append(rng.choice(ASK_REPEAT))
    if p("transfer"):
        texts.append(rng.choice(TRANSFER_HISTORY if rng.random() < 0.4 else TRANSFER))
    if p("promise"):
        amt = rng.choice([30, 80, 120])
        careful = p("check")
        promise = rng.choice(PROMISE_APPROVAL if amt > 50 and p("approval") else PROMISE_PLAIN).format(amt=amt)
        texts += [rng.choice(CHECK), promise] if careful else [promise]
    elif p("check"):
        texts.append(rng.choice(CHECK))
    if p("follow"):
        texts.append(rng.choice(FOLLOW))
    if rng.random() < _p(profile, "close", age):
        texts[-1] += CLOSE
    while len(texts) > customer.MAX_MOVES:                    # the simulator handles six advisor turns: drop a middle one
        texts.pop(rng.randrange(1, len(texts) - 1))
    return greet, texts


def _speech_seconds(text: str) -> float:
    return 1.5 + len(text) / 14


def make_call(rng: random.Random, name: str, age: float) -> tuple[list[dict], dict]:
    profile = PROFILES[name]
    persona = rng.choice(list(customer.PERSONAS))
    difficulty = rng.choice(["EASY", "MEDIUM", "MEDIUM", "HARD"])
    intent = rng.choice(list(customer.INTENTS))
    memory = rng.random() < 0.25
    greet, texts = _script(rng, name, profile, intent, age)
    moves = [customer.read_advisor(t) for t in texts]
    start = customer.replay(persona, None, difficulty, intent, memory, [], [])
    run = customer.replay(persona, None, difficulty, intent, memory, moves, texts)
    turns, t = [], 0.0

    def add(speaker, text, mood=None):
        nonlocal t
        turns.append(dict(speaker=speaker, text=text, start=round(t, 1), end=round(t + _speech_seconds(text), 1), mood=mood))
        t += _speech_seconds(text) + rng.uniform(1, 4)

    if greet:
        add("advisor", greet)
    add("customer", start.opening, start.mood)
    for i, turn in enumerate(run.turns):
        add("advisor", texts[i])
        add("customer", turn.client, turn.mood)
    return turns, (run.outcome or {})


def build(today: dt.date | None = None) -> None:
    today = today or dt.date.today()
    rng = random.Random(20261021)
    calls = []
    for name in PROFILES:
        for _ in range(CALLS_PER_ADVISOR):
            age_days = rng.uniform(0, WEEKS * 7 - 0.5)
            when = dt.datetime.combine(today - dt.timedelta(days=int(age_days)), dt.time(rng.randint(9, 17), rng.randint(0, 59)))
            turns, outcome = make_call(rng, name, age_days / (WEEKS * 7))
            calls.append((when, name, turns, outcome))
    calls.sort(key=lambda c: c[0])
    for n, (when, name, turns, outcome) in enumerate(calls):
        review = quality.review(turns, name, f"CALL-{quality_store.FIRST_ID + n}", source="simulated", outcome=outcome, date=when.date().isoformat())
        quality_store.save(review, created=when.replace(microsecond=0).isoformat())
