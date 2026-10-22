"""Customer advisor agent: reads what the customer says and suggests a sourced answer.

Retrieval is TF-IDF over a small demo knowledge base (knowledge/base.json). Everything the agent says comes from a
passage and its source is listed, so the advisor can check it (explainability). The confidence is the cosine similarity
of the best passage, not a probability. Replace retrieve() with a vector search over the real FAQ when it exists.
"""
import json
import re
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

KB = json.loads((Path(__file__).parent / "knowledge" / "base.json").read_text(encoding="utf-8"))
CUSTOMERS = json.loads((Path(__file__).parent / "knowledge" / "customers.json").read_text(encoding="utf-8"))
_CUSTOMERS_BY_ID = {c["id"]: c for c in CUSTOMERS}
_vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
_matrix = _vec.fit_transform([f"{d['title']}. {d['text']}" for d in KB])

MIN_SCORE = 0.08           # under this the best passage is probably unrelated: say so instead of guessing
REFUND_LIMIT_TND = 50

# intent chips: first words that point to an intent (several can match in one conversation)
INTENT_WORDS = {
    "Billing": r"\b(bill|invoice|charged?|charge|twice|double|payment|refund|amount|fee)\b",
    "Roaming": r"\b(roaming|abroad|travel\w*|country|network)\b",
    "Cancellation": r"\b(cancel\w*|terminate|leave|leaving|quit|early termination)\b",
    "Plan change": r"\b(plan|upgrade|downgrade|bundle|offer|switch)\b",
    "Data usage": r"\b(data|gb|usage|allowance|limit|internet)\b",
    "Complaint": r"\b(complain\w*|unacceptable|unbelievable|angry|furious|dispute)\b",
}


def detect_intents(text: str) -> list[str]:
    return [name for name, rx in INTENT_WORDS.items() if re.search(rx, text, re.I)]


def get_customer(customer_id: str) -> dict | None:
    """Looks up a customer's 360-degree context by id (e.g. "YT-1042"). None if the id is unknown."""
    return _CUSTOMERS_BY_ID.get(customer_id)


def retrieve(query: str, k: int = 3) -> list[tuple[dict, float]]:
    scores = cosine_similarity(_vec.transform([query]), _matrix)[0]
    best = scores.argsort()[::-1][:k]
    return [(KB[i], float(scores[i])) for i in best]


def refund_warning(text: str) -> str | None:
    """A refund above the advisor's limit is flagged when the customer or the advisor mentions the amount."""
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(?:tnd|dinars?|dt)\b", text, re.I):
        if float(m.group(1).replace(",", ".")) > REFUND_LIMIT_TND:
            return f"Refunds above {REFUND_LIMIT_TND} TND need supervisor approval ({m.group(0)} was mentioned)."
    return None


def suggest(query: str, customer_name: str | None = None) -> dict:
    hits = retrieve(query)
    intents = detect_intents(query)
    top, score = hits[0]
    if score < MIN_SCORE:
        return dict(text="I could not find a reliable answer in the knowledge base for this. Please ask the customer to give more details, or escalate to a supervisor.",
                    sources=[], policyWarning=None, confidence=round(score, 2), intents=intents, evidence=[])
    text = top["reply"]
    if customer_name:
        text = f"Hello {customer_name}. " + text
    warning = refund_warning(query) or top.get("policy")
    return dict(
        text=text,
        sources=[d["source"] for d, s in hits if s >= MIN_SCORE],
        policyWarning=warning,
        confidence=round(score, 2),
        intents=intents,
        evidence=[dict(source=d["source"], score=round(s, 2), excerpt=d["title"]) for d, s in hits if s >= MIN_SCORE],
    )


def cosine(a: str, b: str) -> float:
    """TF-IDF cosine similarity of two texts, in the knowledge base's own vocabulary."""
    return float(cosine_similarity(_vec.transform([a]), _vec.transform([b]))[0][0])


# ---- the advisor agent talking by itself (the automatic call)
AUTO_STEPS = ("acknowledge", "check the policy", "give the solution", "follow up in writing")
# a rushed advisor for demonstrations: promises at once, asks the customer to repeat, passes them on. It is what the quality analyst and the complaint agent are there for.
RUSHED = (("promise too early", "I will refund you right away."), ("ask to repeat", "Could you explain the problem again from the start?"),
          ("transfer", "Let me transfer you to the billing team."), ("transfer again", "Please hold while I transfer you to another colleague."))


def _sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", text.strip()) if x.strip()]


def auto_reply(topic: str, turn: int, customer_name: str | None = None, style: str = "careful") -> dict:
    """What the advisor agent says by itself, one step per turn: acknowledge the problem, check the policy, give the solution, confirm in writing.

    The facts come from the same sourced answer the console suggests (`suggest`); the steps are the good practices the quality analyst checks for,
    so an automatic call is the advisor agent's knowledge wrapped in a fixed, honest routine. It is not a language model and it does not read the
    customer's mood: after the last step the call is closed. `turn` counts the advisor's replies so far (0 for the first one).
    """
    if style == "rushed":
        step, text = RUSHED[min(max(turn, 0), len(RUSHED) - 1)]
        return dict(text=text, step=step, turn=turn, last=False, sources=[], intents=detect_intents(topic), policyWarning=None, style=style)
    a = suggest(topic, customer_name)
    step = AUTO_STEPS[min(max(turn, 0), len(AUTO_STEPS) - 1)]
    facts = _sentences(a["text"])
    source = a["sources"][0] if a["sources"] else "our procedure"
    if step == "acknowledge":
        text = "I'm sorry about this, I understand how frustrating it is. " + (facts[0] if facts else "I will look into it now.")
    elif step == "check the policy":
        text = f"Let me check the policy in {source} before I commit to anything."
        if a.get("policyWarning"):
            text += " " + a["policyWarning"]
    elif step == "give the solution":
        text = " ".join(facts[1:3]) if len(facts) > 1 else (facts[0] if facts else "I will take care of it myself.")
    else:
        text = "I will send you a confirmation by email with a reference number and call you back. Is there anything else I can help you with?"
    return dict(text=text[:300], step=step, turn=turn, last=step == AUTO_STEPS[-1], sources=a["sources"], intents=a["intents"], policyWarning=a.get("policyWarning"), style="careful")
