"""Scores the labelling study.

    ../../../venv/Scripts/python.exe -m quality_analyst.labelling.agreement answer-key.json labels-a.json labels-b.json

Every (call, rule) pair is one yes/no question: did this problem happen? The report gives
  1. how much the two people agree with each other (percent and Cohen's kappa: agreement beyond chance, 0 = chance, 1 = perfect),
  2. how the analyst compares with them (precision, recall, F1), against each person and against the consensus (the pairs both people answered the same),
  3. how our own earlier labels compare with them (only on the cases that had labels),
  4. the calls where the two people differ, to discuss before trusting any number.
With one label file only, parts 1 and 4 are skipped. Standard library only.
"""
import json
import sys
from pathlib import Path

from quality_analyst import engine


def kappa(a: list[bool], b: list[bool]) -> float | None:
    n = len(a)
    if not n:
        return None
    observed = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    chance = pa * pb + (1 - pa) * (1 - pb)
    return None if chance == 1 else round((observed - chance) / (1 - chance), 2)


def prf(truth: list[bool], guess: list[bool]) -> dict:
    tp = sum(t and g for t, g in zip(truth, guess))
    fp = sum(g and not t for t, g in zip(truth, guess))
    fn = sum(t and not g for t, g in zip(truth, guess))
    precision, recall = tp / (tp + fp) if tp + fp else None, tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else (0.0 if precision == 0 or recall == 0 else None)
    return dict(tp=tp, fp=fp, fn=fn, precision=precision, recall=recall, f1=f1)


def load(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def answers(labels: dict, ids: list[str]) -> dict[tuple[str, str], bool]:
    """(call, rule) -> ticked, for the calls the labeller marked as done."""
    out = {}
    for cid in ids:
        entry = labels["calls"].get(cid)
        if entry and entry.get("done"):
            for rule in engine.RULES:
                out[(cid, rule)] = rule in entry.get("rules", [])
    return out


def pct(x) -> str:
    return "  n/a" if x is None else f"{100 * x:4.0f}%"


def report(key: dict, label_files: list[dict]) -> str:
    ids = sorted(key["calls"])
    analyst = {(cid, r): r in key["calls"][cid]["analyst"] for cid in ids for r in engine.RULES}
    ours = {(cid, r): r in k["ours"]["expect"] for cid, k in key["calls"].items() if k["ours"] for r in k["ours"]["expect"] + k["ours"]["absent"]}
    people = {lf["labeller"]: answers(lf, ids) for lf in label_files}
    lines = [f"Calls in the sheet: {len(ids)}"]
    for name, a in people.items():
        lines.append(f"  {name}: {len({c for c, _ in a})} calls done")

    def compare(truth: dict, guess: dict, pairs=None):
        keys = [k for k in (pairs or truth) if k in truth and k in guess]
        t, g = [truth[k] for k in keys], [guess[k] for k in keys]
        return keys, t, g

    names = list(people)
    consensus = {}
    if len(names) >= 2:
        a, b = people[names[0]], people[names[1]]
        keys, ta, tb = compare(a, b)
        agree = sum(x == y for x, y in zip(ta, tb)) / len(keys) if keys else None
        lines += ["", f"1. {names[0]} and {names[1]} compared ({len(keys)} yes/no answers)", f"   agree on {pct(agree)} of answers, kappa {kappa(ta, tb)}",
                  "   per rule (kappa is n/a when a rule never occurs or occurs in every call):"]
        for r in engine.RULES:
            rk = [k for k in keys if k[1] == r]
            ra, rb = [a[k] for k in rk], [b[k] for k in rk]
            lines.append(f"   {r:22} agree {pct(sum(x == y for x, y in zip(ra, rb)) / len(rk) if rk else None)}  kappa {kappa(ra, rb)}  (ticked {sum(ra)} / {sum(rb)})")
        consensus = {k: a[k] for k in keys if a[k] == b[k]}
    elif people:
        consensus = dict(next(iter(people.values())))
    basis = "the consensus (answers both people gave)" if len(names) >= 2 else "the single labeller"
    lines += ["", f"2. The analyst against {basis}"]
    if consensus:
        keys, t, g = compare(consensus, analyst)
        s = prf(t, g)
        lines.append(f"   overall: precision {pct(s['precision'])}  recall {pct(s['recall'])}  F1 {pct(s['f1'])}  ({len(keys)} answers; missed {s['fn']}, false alarms {s['fp']})")
        for r in engine.RULES:
            rk = [k for k in keys if k[1] == r]
            rs = prf([consensus[k] for k in rk], [analyst[k] for k in rk])
            if rs["tp"] + rs["fp"] + rs["fn"]:
                lines.append(f"   {r:22} precision {pct(rs['precision'])}  recall {pct(rs['recall'])}  (missed {rs['fn']}, false alarms {rs['fp']})")
        for name, a in people.items():
            keys, t, g = compare(a, analyst)
            lines.append(f"   against {name} alone: F1 {pct(prf(t, g)['f1'])}, kappa {kappa(t, g)}")
        lines += ["", "3. Our own earlier labels against the people (only the cases that had labels)"]
        keys, t, g = compare(consensus, ours)
        if keys:
            lines.append(f"   agree on {pct(sum(x == y for x, y in zip(t, g)) / len(keys))} of {len(keys)} answers, kappa {kappa(t, g)}")
        else:
            lines.append("   no answers in common yet")
    if len(names) >= 2:
        lines += ["", "4. Calls where the two people differ (talk these through first)"]
        a, b = people[names[0]], people[names[1]]
        for cid in ids:
            diff = [r for r in engine.RULES if (cid, r) in a and (cid, r) in b and a[(cid, r)] != b[(cid, r)]]
            if diff:
                lines.append(f"   {cid} ({key['calls'][cid]['source']}): " + ", ".join(f"{r} ({names[0]} {'yes' if a[(cid, r)] else 'no'}, {names[1]} {'yes' if b[(cid, r)] else 'no'}, analyst {'yes' if analyst[(cid, r)] else 'no'})" for r in diff))
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    print(report(load(sys.argv[1]), [load(p) for p in sys.argv[2:]]))
