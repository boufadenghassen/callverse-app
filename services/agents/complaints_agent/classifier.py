"""Hybrid, explainable complaint classification.

Rules take precedence for high-signal phrases. TF-IDF is used only when no
rule matches, so uncertain language is returned as ``other`` rather than
being forced into a misleading category.
"""
import re
import os
from pathlib import Path

from . import rules

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:  # pragma: no cover - requirements install sklearn
    TfidfVectorizer = None
    cosine_similarity = None

_MIN_SIMILARITY = 0.16
_MIN_MODEL_CONFIDENCE = 0.55
_DATASET_TO_OPERATIONAL = {
    "BILLING": "billing_amount",
    "CONTRACT_PLAN": "contract_terms",
    "CUSTOMER_SERVICE": "repeat_contact",
    "FIELD_SERVICE": "device",
    "FRAUD_PRIVACY_LEGAL": "other",
    "NETWORK_TECH": "network",
    "OTHER_UNCLEAR": "other",
    "POLICY_COMPETITION": "other",
}
_MODEL_PATH = os.environ.get("COMPLAINTS_MODEL_PATH")
_supervised = None
if _MODEL_PATH and Path(_MODEL_PATH).is_file():
    from .ml_model import load
    _supervised = load(_MODEL_PATH)


def _prototype(cluster: dict) -> str:
    pattern = re.sub(r"[\\()?$+*{}\[\]|]", " ", cluster["rx"])
    return " ".join([cluster["label"], cluster["cause"], cluster["action"], pattern]).strip()


_keys = list(rules.CLUSTERS)
_patterns = {key: re.compile(value["rx"], re.I) for key, value in rules.CLUSTERS.items()}
_vectorizer = None
_prototypes = None
if TfidfVectorizer is not None:
    _vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
    _prototypes = _vectorizer.fit_transform([_prototype(rules.CLUSTERS[key]) for key in _keys])


def classify(text: str) -> dict:
    """Return the category, confidence, evidence and method for one complaint."""
    hits = {key: len(pattern.findall(text)) for key, pattern in _patterns.items()}
    matched = sorted((key for key, count in hits.items() if count), key=lambda key: -hits[key])
    if matched:
        key = matched[0]
        evidence = _patterns[key].search(text)
        return {
            "key": key,
            "other": matched[1:],
            "similarity": 1.0,
            "matchedWord": evidence.group(0).strip().lower() if evidence else None,
            "method": "rules",
        }

    if _supervised is not None and text.strip():
        probabilities = _supervised.predict_proba([text])[0]
        index = int(probabilities.argmax())
        score = float(probabilities[index])
        if score >= _MIN_MODEL_CONFIDENCE:
            dataset_label = str(_supervised.classes_[index])
            return {
                "key": _DATASET_TO_OPERATIONAL.get(dataset_label, "other"),
                "other": [],
                "similarity": round(score, 3),
                "matchedWord": None,
                "method": "supervised",
                "datasetLabel": dataset_label,
            }

    if _vectorizer is not None and _prototypes is not None and text.strip():
        scores = cosine_similarity(_vectorizer.transform([text]), _prototypes)[0]
        index = int(scores.argmax())
        score = float(scores[index])
        if score >= _MIN_SIMILARITY:
            return {
                "key": _keys[index],
                "other": [],
                "similarity": round(score, 3),
                "matchedWord": None,
                "method": "tfidf",
            }

    return {"key": "other", "other": [], "similarity": 0.0, "matchedWord": None, "method": "unclassified"}
