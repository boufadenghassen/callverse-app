"""Supervised complaint classifier training and inference.

The training CSV must contain ``text`` and either ``label`` or ``label_final``.
The Comcast gold file uses ``label_final``.
"""
import csv
import json
import math
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


def read_labeled_csv(path: str | Path) -> tuple[list[str], list[str]]:
    texts, labels = [], []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            text = (row.get("text") or "").strip()
            label = (row.get("label_final") or row.get("label") or "").strip()
            if text and label:
                texts.append(text)
                labels.append(label)
    if len(set(labels)) < 2:
        raise ValueError("The labeled dataset must contain at least two classes.")
    return texts, labels


def build_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char", ngram_range=(3, 5), sublinear_tf=True, min_df=1)),
        ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])


def train(path: str | Path, model_path: str | Path, test_size: float = 0.2, seed: int = 42) -> dict:
    texts, labels = read_labeled_csv(path)
    counts = {label: labels.count(label) for label in sorted(set(labels))}
    if min(counts.values()) < 2:
        raise ValueError("Each class needs at least two examples for a stratified split.")
    classes = len(counts)
    test_count = max(classes, math.ceil(len(labels) * test_size))
    if len(labels) - test_count < classes:
        raise ValueError("The labeled dataset is too small for a stratified train/test split.")
    x_train, x_test, y_train, y_test = train_test_split(
        texts, labels, test_size=test_count, random_state=seed, stratify=labels
    )
    model = build_pipeline()
    model.fit(x_train, y_train)
    predicted = model.predict(x_test)
    names = sorted(set(labels))
    metrics = {
        "samples": len(labels),
        "trainSamples": len(x_train),
        "testSamples": len(x_test),
        "classes": names,
        "classCounts": counts,
        "accuracy": round(float(accuracy_score(y_test, predicted)), 4),
        "macroF1": round(float(f1_score(y_test, predicted, labels=names, average="macro", zero_division=0)), 4),
        "report": classification_report(y_test, predicted, labels=names, output_dict=True, zero_division=0),
        "confusionMatrix": confusion_matrix(y_test, predicted, labels=names).tolist(),
        "seed": seed,
        "source": str(path),
        "labelColumn": "label_final" if any("label_final" in row for row in _read_rows(path)) else "label",
    }
    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    import joblib
    joblib.dump(model, model_path)
    metrics_path = model_path.with_suffix(".metrics.json")
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def _read_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def load(model_path: str | Path):
    import joblib
    return joblib.load(model_path)
