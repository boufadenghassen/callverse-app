"""Occlusion explanation, tested with a fake model (no weights needed). Run from the repo root: pytest -q models/tests"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import explain  # noqa: E402

SR = 100


def fake_model(waves):
    """Class 0 ('anger') gets more likely the more energy the window holds; class 1 gets the rest."""
    out = []
    for w in waves:
        p0 = float(np.clip(np.abs(w).mean(), 0, 1))
        out.append([p0, 1 - p0])
    return np.array(out)


def setup(y):
    n = max(1, round(len(y) / (3 * SR)))
    bounds = np.linspace(0, len(y), n + 1).astype(int)
    proba = fake_model([y[a:b] for a, b in zip(bounds[:-1], bounds[1:])])
    return bounds, proba


def test_silencing_the_only_loud_part_costs_the_most():
    y = np.zeros(6 * SR)
    y[3 * SR:4 * SR] = 1.0                                   # the only energy: second 3 to 4
    bounds, proba = setup(y)
    blocks = explain.occlusion(y, SR, bounds, proba, 0, fake_model, 0.5)
    assert len(blocks) == 12 and blocks[0]["startSec"] == 0 and blocks[-1]["endSec"] == 6
    loud = [b for b in blocks if 3 <= b["startSec"] < 4]
    quiet = [b for b in blocks if b["startSec"] < 3 or b["startSec"] >= 4]
    assert all(b["drop"] > 0 for b in loud) and all(b["drop"] == 0 for b in quiet)
    s = explain.summarize(blocks)
    assert {t["startSec"] for t in s["top"]} <= {3.0, 3.5} and max(b["rel"] for b in s["blocks"]) == 1.0


def test_a_block_that_argues_against_the_answer_gets_a_negative_drop():
    y = np.full(3 * SR, 0.5)
    bounds, _ = setup(y)
    proba = np.array([[0.5, 0.5]])
    contrary = lambda waves: np.array([[0.9, 0.1] for _ in waves])        # silencing anything makes class 0 MORE likely
    blocks = explain.occlusion(y, SR, bounds, proba, 0, contrary, 1.0)
    assert all(b["drop"] < 0 for b in blocks)
    assert explain.summarize(blocks)["top"] == []


def test_a_block_that_straddles_two_windows_rescores_both():
    y = np.ones(6 * SR)
    bounds, proba = setup(y)
    seen = []
    blocks = explain.occlusion(y, SR, bounds, proba, 0, lambda w: (seen.append(len(w)), fake_model(w))[1], 1.0)
    assert len(blocks) == 6
    y2 = np.ones(5 * SR)                                     # 2 windows of 2.5 s; a 1 s block starting at 2 s touches both
    bounds2, proba2 = setup(y2)
    jobs = []
    explain.occlusion(y2, SR, bounds2, proba2, 0, lambda w: (jobs.append(len(w)), fake_model(w))[1], 1.0)
    assert jobs[0] == 6                                      # 5 blocks, one of them counted twice


def test_long_calls_get_longer_blocks():
    assert explain.block_seconds(10) == 0.25
    assert explain.block_seconds(120) == 2.5
