"""How accurate is the quality analyst? Runs the hand-labelled calls of eval_cases.py through engine.review().

For every rule: true positives (expected and found), false negatives (expected, missed), false alarms (must stay silent, fired) and true negatives,
then precision, recall and F1. `split` picks the development cases, the held-out test cases or all of them. Run it as a script for a report:
    ../../../venv/Scripts/python.exe -m quality_analyst.evaluation
"""
import functools

from . import engine as quality
from . import eval_cases as data


def evaluate(split: str | None = None) -> dict:
    cases = [c for c in data.CASES if split in (None, c["split"])]
    stats = {r: dict(tp=0, fn=0, fp=0, tn=0) for r in quality.RULES}
    mistakes = []
    for c in cases:
        fired = {e["rule"] for e in quality.review(c["turns"], "Eval", c["id"])["errors"]}
        for rule in c["expect"]:
            hit = rule in fired
            stats[rule]["tp" if hit else "fn"] += 1
            if not hit:
                mistakes.append(dict(case=c["id"], rule=rule, kind="missed"))
        for rule in c["absent"]:
            hit = rule in fired
            stats[rule]["fp" if hit else "tn"] += 1
            if hit:
                mistakes.append(dict(case=c["id"], rule=rule, kind="false alarm"))
    rules = []
    for rule, s in stats.items():
        judged = s["tp"] + s["fn"] + s["fp"] + s["tn"]
        if not judged:
            continue
        precision = s["tp"] / (s["tp"] + s["fp"]) if s["tp"] + s["fp"] else None
        recall = s["tp"] / (s["tp"] + s["fn"]) if s["tp"] + s["fn"] else None
        f1 = 2 * precision * recall / (precision + recall) if precision and recall else (0.0 if precision == 0 or recall == 0 else None)
        rules.append(dict(rule=rule, label=quality.RULE_LABELS[rule], **s, judged=judged,
                          precision=None if precision is None else round(precision, 2), recall=None if recall is None else round(recall, 2), f1=None if f1 is None else round(f1, 2)))
    tp, fn, fp, tn = (sum(s[k] for s in stats.values()) for k in ("tp", "fn", "fp", "tn"))
    precision, recall = tp / (tp + fp) if tp + fp else 0.0, tp / (tp + fn) if tp + fn else 0.0
    return dict(split=split or "all", cases=len(cases), judgements=tp + fn + fp + tn,
                precision=round(precision, 3), recall=round(recall, 3), f1=round(2 * precision * recall / (precision + recall), 3) if precision + recall else 0.0,
                accuracy=round((tp + tn) / (tp + fn + fp + tn), 3), rules=sorted(rules, key=lambda r: (r["f1"] is None, r["f1"])), mistakes=mistakes)


if __name__ == "__main__":
    for split in ("dev", "test"):
        r = evaluate(split)
        print(f"\n== {split}: {r['cases']} calls, {r['judgements']} judgements | precision {r['precision']:.0%} recall {r['recall']:.0%} F1 {r['f1']:.0%} accuracy {r['accuracy']:.0%}")
        for x in r["rules"]:
            print(f"  {x['rule']:22s} P {x['precision']}  R {x['recall']}  F1 {x['f1']}   (tp {x['tp']} fn {x['fn']} fp {x['fp']} tn {x['tn']})")
        for m in r["mistakes"]:
            print("   !", m["case"], m["rule"], m["kind"])


def tune(grid=(0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75), passes=2) -> dict:
    """Choose each move's similarity threshold on the DEVELOPMENT calls only: the value with the best F1 (the middle one when several tie)."""
    from . import semantic
    best_f1 = evaluate("dev")["f1"]
    for _ in range(passes):
        for move in semantic.PROTOTYPES:
            results = {}
            for t in grid:
                semantic.THRESHOLDS[move] = t
                results[t] = evaluate("dev")["f1"]
            top = max(results.values())
            winners = sorted(t for t, f in results.items() if f >= top - 1e-9)
            semantic.THRESHOLDS[move] = winners[len(winners) // 2]
        best_f1 = evaluate("dev")["f1"]
    return dict(thresholds=dict(semantic.THRESHOLDS), dev_f1=best_f1)


JOURNEY = [
    "First measure, keyword rules only, on 72 hand-labelled development calls: F1 84 %.",
    "First measure on 44 harder calls it had never seen (paraphrases, denials, new wording): keyword rules F1 75 %, with the semantic second opinion F1 81 %.",
    "Those misses were used to widen the phrase lists and the semantic prototypes in general ways (the calls became development calls), the thresholds were tuned on development calls only.",
    "Final measure on held-out test calls, 51 of them written before that work and never looked at: keyword rules F1 98 %, with the semantic second opinion F1 99 %.",
]
LIMITS = ("The calls are written by us and short, the labels are our own judgement, and a call set this size gives a rough score, not a guarantee: a few calls move a rule's recall by "
          "10 points. Real calls will be harder (Arabic, French, noise, long calls). Mood-based rules are checked on given moods, so they only test the thresholds.")


@functools.lru_cache(maxsize=1)
def report() -> dict:
    """The accuracy report shown on the Quality page. Deterministic for a given set of rules and cases, so it is computed once."""
    from . import semantic
    dev, test = evaluate("dev"), evaluate("test")
    by_id = {c["id"]: c for c in data.CASES}
    for e in (dev, test):
        for m in e["mistakes"]:
            call = by_id[m["case"]]
            m["text"] = " / ".join(t["text"] for t in call["turns"] if t["speaker"] == "advisor")[:160]
    return dict(semantic=quality.SEMANTIC, thresholds=dict(semantic.THRESHOLDS) if quality.SEMANTIC else None, dev=dev, test=test, journey=JOURNEY, limits=LIMITS)
