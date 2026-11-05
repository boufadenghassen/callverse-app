"""Train reproducible public-telecom baseline models.

IBM Telco is deployable here because tenure and monthly charge map to the
advisor profile. KDD Cup 2009 remains an offline upsell benchmark: its fields
are anonymised and must not be presented as explanations for Callverse users.
Run ``py -m sales_agent.public_models`` from ``services/agents``.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import joblib
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("SALES_PUBLIC_DATA_DIR", ROOT / "data" / "public"))
MODEL_DIR = Path(os.environ.get("SALES_PUBLIC_MODEL_DIR", ROOT / "data" / "models"))
IBM_MODEL, KDD_MODEL = "ibm_telco_churn.joblib", "kdd_orange_upsell.joblib"


def _fit(x: np.ndarray, y: np.ndarray):
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                         LogisticRegression(max_iter=1_000, class_weight="balanced", random_state=7)).fit(x, y)


def train_ibm(path: Path | None = None, output_dir: Path | None = None) -> dict:
    """Train the online model using only fields available to this agent."""
    path, output_dir = path or DATA_DIR / "Telco-Customer-Churn.csv", output_dir or MODEL_DIR
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    x = np.array([[float(r["tenure"]), float(r["MonthlyCharges"])] for r in rows])
    y = np.array([r["Churn"] == "Yes" for r in rows])
    tx, vx, ty, vy = train_test_split(x, y, test_size=.25, stratify=y, random_state=7)
    model = _fit(tx, ty)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact = output_dir / IBM_MODEL
    joblib.dump(model, artifact)
    return {"dataset": "IBM Telco Customer Churn", "rows": len(rows), "features": ["tenureMonths", "monthlyCharge"],
            "testAuc": round(float(roc_auc_score(vy, model.predict_proba(vx)[:, 1])), 3), "model": str(artifact)}


def train_kdd_upsell(path: Path | None = None, labels: Path | None = None, output_dir: Path | None = None) -> dict:
    """Train an offline Orange upsell benchmark from its 190 numeric fields."""
    path = path or DATA_DIR / "orange_small_train" / "orange_small_train.data"
    labels, output_dir = labels or DATA_DIR / "orange_small_train_upselling.labels", output_dir or MODEL_DIR
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t"); next(reader)
        x = np.array([[float(v) if v else np.nan for v in row[:190]] for row in reader], dtype=float)
    # The published label files use ``1`` / ``-1`` (not ``+1`` / ``-1``).
    y = np.array([s.strip() == "1" for s in labels.read_text(encoding="utf-8").splitlines()])
    tx, vx, ty, vy = train_test_split(x, y, test_size=.25, stratify=y, random_state=7)
    model = _fit(tx, ty)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact = output_dir / KDD_MODEL
    joblib.dump(model, artifact)
    return {"dataset": "KDD Cup 2009 Orange", "rows": len(y), "features": 190, "target": "upselling",
            "testAuc": round(float(roc_auc_score(vy, model.predict_proba(vx)[:, 1])), 3), "model": str(artifact),
            "limitation": "Anonymised fields: benchmark only, never a Callverse explanation."}


def ibm_churn_probability(tenure_years: float | None, monthly_charge: float | None) -> float | None:
    artifact = MODEL_DIR / IBM_MODEL
    if tenure_years is None or monthly_charge is None or not artifact.exists():
        return None
    model = joblib.load(artifact)
    return round(float(model.predict_proba([[max(0, tenure_years * 12), max(0, monthly_charge)]])[0, 1]), 3)


if __name__ == "__main__":
    print(json.dumps({"ibm": train_ibm(), "kdd": train_kdd_upsell()}, indent=2))
