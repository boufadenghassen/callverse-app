"""Which parts of a recording made the emotion model say what it said? (occlusion, an explanation that needs no access to the model's insides)

Silence one short block of the recording at a time, score the clip again, and see how much the probability of the answer falls. A block whose removal
makes the answer much less likely is a block the model leaned on; a block whose removal makes it MORE likely argued against the answer.
This shows where the model looked, not a proof of why: it is a sensitivity map, and the model was trained on acted speech.
Pure numpy on purpose: serve.py gives it the model's scoring function, the tests give it a fake one.
"""
import numpy as np

MAX_BLOCKS = 48           # a long call gets longer blocks, so the cost stays bounded
MIN_BLOCK_SEC = 0.25


def block_seconds(duration_sec: float) -> float:
    return max(MIN_BLOCK_SEC, round(duration_sec / MAX_BLOCKS, 2))


def occlusion(y: np.ndarray, sr: int, bounds: np.ndarray, proba: np.ndarray, best: int, rescore, block_sec: float) -> list[dict]:
    """y: the clip; bounds: sample edges of the scoring windows (n + 1 numbers); proba: (n, classes) calibrated probabilities of those windows;
    best: the class being explained; rescore(list of waves) -> calibrated (len, classes) probabilities.
    Returns one dict per block: startSec, endSec and drop = fall of the clip's probability for `best` when the block is silenced."""
    n = len(bounds) - 1
    size = max(1, int(block_sec * sr))
    base = float(proba.mean(0)[best])
    spans, jobs = [], []                              # a block can touch two windows: every touched window is scored again
    for a in range(0, len(y), size):
        b = min(a + size, len(y))
        touched = []
        for w in range(n):
            lo, hi = max(a, int(bounds[w])), min(b, int(bounds[w + 1]))
            if lo < hi:
                x = y[int(bounds[w]):int(bounds[w + 1])].copy()
                x[lo - int(bounds[w]):hi - int(bounds[w])] = 0.0
                touched.append((len(jobs), w))
                jobs.append(x)
        spans.append((a, b, touched))
    new = rescore(jobs)
    blocks = []
    for a, b, touched in spans:
        total = float(proba[:, best].sum())
        for j, w in touched:
            total += float(new[j][best]) - float(proba[w, best])
        blocks.append(dict(startSec=round(a / sr, 2), endSec=round(b / sr, 2), drop=round(base - total / n, 4)))
    return blocks


def summarize(blocks: list[dict], top: int = 3) -> dict:
    """Adds rel (drop scaled to -1..1 by the biggest one) to each block and lists the most influential moments."""
    peak = max((abs(b["drop"]) for b in blocks), default=0.0)
    for b in blocks:
        b["rel"] = round(b["drop"] / peak, 3) if peak > 0 else 0.0
    best = sorted((b for b in blocks if b["drop"] > 0), key=lambda b: -b["drop"])[:top]
    return dict(blocks=blocks, top=[dict(startSec=b["startSec"], endSec=b["endSec"], drop=b["drop"]) for b in best])
