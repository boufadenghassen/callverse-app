"""Customer advisor agent: reads what the customer says and suggests a sourced answer.

Retrieval is TF-IDF over a small demo knowledge base (knowledge/base.json). Everything the agent says comes from a
passage and its source is listed, so the advisor can check it (explainability). The confidence is the cosine similarity
of the best passage, not a probability. Replace retrieve() with a vector search over the real FAQ when it exists.
"""
import json
import math
import re
from collections import Counter
from pathlib import Path

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except (ImportError, ValueError):
    class TfidfVectorizer:
        """Small fallback for environments with broken optional sklearn binaries."""

        def __init__(self, **_options):
            self.vocabulary: dict[str, int] = {}
            self.idf: list[float] = []

        @staticmethod
        def _terms(text: str) -> list[str]:
            words = re.findall(r"[a-z0-9]+", text.lower())
            return words + [f"{a} {b}" for a, b in zip(words, words[1:])]

        def fit_transform(self, texts: list[str]):
            documents = [self._terms(text) for text in texts]
            all_terms = sorted({term for terms in documents for term in terms})
            self.vocabulary = {term: index for index, term in enumerate(all_terms)}
            total = len(documents)
            self.idf = [
                math.log((1 + total) / (1 + sum(term in terms for terms in documents))) + 1
                for term in all_terms
            ]
            return self.transform(texts)

        def transform(self, texts: list[str]):
            vectors = []
            for text in texts:
                counts = Counter(self._terms(text))
                vector = [0.0] * len(self.vocabulary)
                for term, count in counts.items():
                    if term in self.vocabulary:
                        vector[self.vocabulary[term]] = (1 + math.log(count)) * self.idf[self.vocabulary[term]]
                norm = math.sqrt(sum(value * value for value in vector)) or 1.0
                vectors.append([value / norm for value in vector])
            return vectors

    def cosine_similarity(left, right):
        return [[sum(a * b for a, b in zip(row, candidate)) for candidate in right] for row in left]

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
    best = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)[:k]
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
