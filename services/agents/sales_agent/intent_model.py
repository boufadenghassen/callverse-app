"""Local, trainable multi-label intent model for the sales agent.

The model deliberately has no network or vendor dependency.  It learns from
labelled customer utterances using TF-IDF word and character features and a
one-vs-rest logistic-regression classifier.  A deployment can point
``SALES_TRAINING_DATA`` at an approved JSON export of labelled conversations;
the small checked-in corpus is only a bootstrapping corpus for the demo.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import FeatureUnion
from sklearn.preprocessing import MultiLabelBinarizer


HERE = Path(__file__).resolve().parent
DEFAULT_DATA = HERE / "training_examples.json"
# Calibrated against the bundled hold-out-style paraphrase tests.  Keeping this
# above the common 0.2--0.3 background probability prevents a weakly related
# label from becoming a commercial recommendation.
THRESHOLD = 0.45


def _training_path() -> Path:
    """Use an approved deployment corpus when supplied, otherwise the demo seed."""
    return Path(os.environ.get("SALES_TRAINING_DATA", DEFAULT_DATA))


def _load_examples(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("sales training data must be a JSON array")
    examples = []
    for row in raw:
        text, needs = row.get("text"), row.get("needs")
        if isinstance(text, str) and text.strip() and isinstance(needs, list) and all(isinstance(n, str) for n in needs):
            examples.append({"text": text.strip(), "needs": needs})
    if len(examples) < 20:
        raise ValueError("sales training data needs at least 20 labelled utterances")
    return examples


class IntentModel:
    """A fitted multi-label intent classifier with confidence scores."""

    def __init__(self, examples: list[dict]):
        self.labels = MultiLabelBinarizer()
        y = self.labels.fit_transform([row["needs"] for row in examples])
        features = FeatureUnion([
            ("words", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, strip_accents="unicode")),
            ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1)),
        ])
        self.pipeline = features
        x = self.pipeline.fit_transform([row["text"] for row in examples])
        self.classifier = OneVsRestClassifier(LogisticRegression(max_iter=1000, class_weight="balanced", random_state=7))
        self.classifier.fit(x, y)

    def predict(self, text: str, threshold: float = THRESHOLD) -> dict[str, float]:
        """Return all needs above the confidence threshold, best first."""
        probabilities = self.classifier.predict_proba(self.pipeline.transform([text]))[0]
        found = [(label, float(p)) for label, p in zip(self.labels.classes_, probabilities) if p >= threshold]
        return dict(sorted(found, key=lambda item: -item[1]))


@lru_cache(maxsize=4)
def load_model(path_text: str | None = None) -> IntentModel:
    """Load once per corpus path; useful in FastAPI's long-lived worker."""
    path = Path(path_text) if path_text else _training_path()
    return IntentModel(_load_examples(path))


def predict(text: str) -> dict[str, float]:
    return load_model(str(_training_path())).predict(text)
