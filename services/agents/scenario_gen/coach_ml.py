"""Local ML model for mapping QA weaknesses to training skills.

The project does not yet have enough labelled historical coach plans to train from
production data. Until that dataset exists, this model is fitted at startup from
deterministic, augmented examples generated from the catalog's reviewed mappings.
The model is deliberately limited to plan structure; scenario facts and wording
remain catalog/template data.
"""
from __future__ import annotations

import random
import json
import os
import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .catalog import Catalog, normalize_key
from .schemas import FocusItem, QAWeakness


@dataclass
class _Node:
    value: np.ndarray
    feature: int | None = None
    threshold: float | None = None
    left: "_Node | None" = None
    right: "_Node | None" = None


class _FallbackForest:
    """Small dependency-free regression forest used when sklearn cannot import."""

    def __init__(self, seed: int, trees: int = 80, depth: int = 8):
        self.rng = random.Random(seed)
        self.trees = trees
        self.depth = depth
        self.roots: list[_Node] = []

    def fit(self, x: np.ndarray, y: np.ndarray) -> None:
        self.roots = []
        for _ in range(self.trees):
            indices = [self.rng.randrange(len(x)) for _ in range(len(x))]
            self.roots.append(self._grow(x, y, indices, 0))

    def _grow(self, x, y, indices, depth: int) -> _Node:
        values = y[indices]
        node = _Node(np.mean(values, axis=0))
        if depth >= self.depth or len(indices) < 4:
            return node
        features = list(range(x.shape[1]))
        self.rng.shuffle(features)
        best = None
        parent_error = float(np.sum((values - node.value) ** 2))
        for feature in features[: max(2, int(len(features) ** 0.5))]:
            candidates = sorted({float(x[i, feature]) for i in indices})
            if len(candidates) < 2:
                continue
            for threshold in self.rng.sample(candidates[:-1], min(8, len(candidates) - 1)):
                left = [i for i in indices if x[i, feature] <= threshold]
                right = [i for i in indices if x[i, feature] > threshold]
                if len(left) < 2 or len(right) < 2:
                    continue
                error = float(
                    np.sum((y[left] - np.mean(y[left], axis=0)) ** 2)
                    + np.sum((y[right] - np.mean(y[right], axis=0)) ** 2)
                )
                if best is None or error < best[0]:
                    best = (error, feature, threshold, left, right)
        if best is None or best[0] >= parent_error:
            return node
        _, feature, threshold, left, right = best
        node.feature, node.threshold = feature, threshold
        node.left, node.right = self._grow(x, y, left, depth + 1), self._grow(x, y, right, depth + 1)
        return node

    def predict(self, x: np.ndarray) -> np.ndarray:
        def walk(node, row):
            if node.feature is None:
                return node.value
            return walk(node.left if row[node.feature] <= node.threshold else node.right, row)

        return np.asarray([np.mean([walk(root, row) for root in self.roots], axis=0) for row in x])


class _LeastSquares:
    """Multi-output linear regression (ridge, closed form, numpy only): one weight per QA criterion and skill.

    The coach's target is a weighted sum of how far each criterion is from perfect, so a linear model has the right shape,
    needs no extra package, and its weights can be read back (each one says how much a criterion's gap feeds a skill's gap)."""

    def __init__(self, ridge: float = 1e-3):
        self.ridge = ridge
        self.weights: np.ndarray | None = None

    @staticmethod
    def _with_bias(x: np.ndarray) -> np.ndarray:
        return np.hstack([x, np.ones((len(x), 1))])

    def fit(self, x: np.ndarray, y: np.ndarray) -> None:
        a = self._with_bias(x)
        self.weights = np.linalg.solve(a.T @ a + self.ridge * np.eye(a.shape[1]), a.T @ y)

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self._with_bias(np.asarray(x, dtype=float)) @ self.weights


class CoachMLModel:
    """Predicts skill gaps (0 = fine, 1 = the whole skill is missing) from QA criterion scores.

    Two candidates are trained and scored on the same held-out examples: a linear model and a random forest. The one with
    the better R2 is kept (`name`), and both scores are reported (`linear_*`, `forest_*` in `metrics`)."""

    SAMPLES = 2000
    name = "RandomForestRegressor"
    artifact_path = Path(__file__).resolve().parents[3] / "models" / "coach" / "coach_model.pkl"
    metrics_path = Path(__file__).resolve().parents[3] / "models" / "coach" / "coach_metrics.json"

    def __init__(self, catalog: Catalog, seed: int = 17):
        self.catalog = catalog
        self.criteria = sorted(catalog.criteria)
        self.skills = sorted(catalog.skills)
        self._criterion_index = {name: index for index, name in enumerate(self.criteria)}
        self._skill_index = {name: index for index, name in enumerate(self.skills)}
        self.implementation = "scikit-learn" if self._sklearn_available() else "built-in fallback"
        # a skill's gap is divided by the most its criteria can add up to, so every gap is on the same 0..1 scale as the prediction
        self._max_gap = np.ones(len(self.skills))
        for mappings in catalog.criteria.values():
            for skill, weight in mappings:
                self._max_gap[self._skill_index[skill]] += weight
        self._max_gap -= 1
        self._max_gap[self._max_gap <= 0] = 1.0
        self.model = self._new_model(seed)
        self.metrics = self._fit_and_evaluate(seed)
        self._save_artifacts(seed)

    def _new_model(self, seed: int):
        if self.implementation == "scikit-learn":
            return RandomForestRegressor(
                n_estimators=120, max_depth=8, min_samples_leaf=2, random_state=seed, n_jobs=1
            )
        return _FallbackForest(seed)

    @staticmethod
    def _sklearn_available() -> bool:
        try:
            from sklearn.ensemble import RandomForestRegressor
            globals()["RandomForestRegressor"] = RandomForestRegressor
            return True
        except (ImportError, ValueError):
            return False

    def _dataset(self, seed: int) -> tuple[np.ndarray, np.ndarray]:
        rng = random.Random(seed)
        rows: list[list[float]] = []
        targets: list[list[float]] = []
        # Augmentation makes the forest learn the mapping across the complete score range.
        for _ in range(self.SAMPLES):
            scores = {criterion: rng.random() for criterion in self.criteria}
            rows.append([scores[criterion] for criterion in self.criteria])
            target = [0.0] * len(self.skills)
            for criterion, mappings in self.catalog.criteria.items():
                severity = 1.0 - scores[criterion]
                for skill, weight in mappings:
                    target[self._skill_index[skill]] += severity * weight
            targets.append(target)
        return np.asarray(rows), np.asarray(targets) / self._max_gap

    @staticmethod
    def _score(model, train_x, train_y, test_x, test_y) -> dict[str, float]:
        model.fit(train_x, train_y)
        predicted = np.clip(model.predict(test_x), 0.0, 1.0)
        errors = predicted - test_y
        variance = float(np.sum((test_y - np.mean(test_y, axis=0)) ** 2))
        top3_true = np.argsort(test_y, axis=1)[:, ::-1][:, :3]
        top3_pred = np.argsort(predicted, axis=1)[:, ::-1][:, :3]
        overlap = np.mean([len(set(a) & set(b)) / 3 for a, b in zip(top3_true, top3_pred)])
        return {
            "mae": round(float(np.mean(np.abs(errors))), 4),
            "rmse": round(float(np.sqrt(np.mean(errors ** 2))), 4),
            "r2": round(1.0 - float(np.sum(errors ** 2)) / variance if variance else 0.0, 4),
            "top_skill_accuracy": round(float(np.mean(np.argmax(predicted, axis=1) == np.argmax(test_y, axis=1))), 4),
            "top3_overlap": round(float(overlap), 4),
        }

    def _fit_and_evaluate(self, seed: int) -> dict[str, float | int | str]:
        features, targets = self._dataset(seed)
        split = int(len(features) * 0.8)
        train_x, test_x = features[:split], features[split:]
        train_y, test_y = targets[:split], targets[split:]
        forest_name = "RandomForestRegressor" + ("" if self.implementation == "scikit-learn" else " (built-in)")
        candidates = {
            "LinearRegression (least squares)": (_LeastSquares, self._score(_LeastSquares(), train_x, train_y, test_x, test_y)),
            forest_name: (lambda: self._new_model(seed), self._score(self._new_model(seed + 1), train_x, train_y, test_x, test_y)),
        }
        best = max(candidates, key=lambda key: candidates[key][1]["r2"])
        self.name = best
        self.model = candidates[best][0]()
        self.model.fit(features, targets)
        return {
            "dataset": "synthetic_catalog_v2",
            "samples": len(features),
            "train_samples": len(train_x),
            "test_samples": len(test_x),
            **candidates[best][1],
            "implementation": self.implementation,
            **{f"{'linear' if key.startswith('Linear') else 'forest'}_{metric}": value[1][metric]
               for key, value in candidates.items() for metric in ("r2", "mae", "top_skill_accuracy")},
            "target_scale": "skill gap 0..1 (divided by the total weight of the criteria that feed the skill)",
            "note": "Synthetic examples from the catalog's reviewed criterion-to-skill weights: the score says the model "
                    "reproduces that mapping, not that it matches real coaching decisions (that needs plans labelled by supervisors).",
        }

    def _save_artifacts(self, seed: int) -> None:
        self.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.artifact_path.exists() or os.getenv("COACH_RETRAIN_ARTIFACT") == "1":
            with self.artifact_path.open("wb") as handle:
                pickle.dump(
                    {
                        "model": self.model,
                        "criteria": self.criteria,
                        "skills": self.skills,
                        "seed": seed,
                        "metrics": self.metrics,
                    },
                    handle,
                    protocol=pickle.HIGHEST_PROTOCOL,
                )
        self.metrics_path.write_text(
            json.dumps(
                {
                    "model": self.name,
                    "features": self.criteria,
                    "targets": self.skills,
                    "metrics": self.metrics,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _unit_score(score: float) -> float:
        return score if score <= 1 else score / 100.0

    def analyze(
        self, weaknesses: list[QAWeakness], threshold: float, max_skills: int
    ) -> tuple[list[FocusItem], list[str]]:
        scores = {criterion: 1.0 for criterion in self.criteria}
        criteria_for_skill: dict[str, list[str]] = {skill: [] for skill in self.skills}
        notes: list[str] = []
        for item in weaknesses:
            key = normalize_key(item.criterion)
            mappings = self.catalog.criterion_to_skills(item.criterion)
            if mappings is None:
                notes.append(f"Ignored unknown QA criterion '{item.criterion}'.")
                continue
            score = self._unit_score(item.score)
            if score >= threshold:
                continue
            canonical = key if key in self._criterion_index else next(
                (criterion for criterion, pairs in self.catalog.criteria.items() if pairs == mappings), None
            )
            if canonical in self._criterion_index:
                scores[canonical] = min(scores[canonical], score)
            for skill, _ in mappings:
                criteria_for_skill[skill].append(item.criterion)

        predicted = self.model.predict(
            np.asarray([[scores[criterion] for criterion in self.criteria]])
        )[0]
        ranked: list[FocusItem] = []
        for skill_index in np.argsort(predicted)[::-1]:
            skill = self.skills[int(skill_index)]
            gap = round(float(np.clip(predicted[skill_index], 0.0, 1.0)), 3)
            if gap <= 0 or not criteria_for_skill[skill]:
                continue
            ranked.append(FocusItem(skill=skill, gap=gap, criteria=criteria_for_skill[skill]))
        return ranked[:max_skills], notes
