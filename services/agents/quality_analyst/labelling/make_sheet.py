"""Builds the blind labelling sheet for the human-agreement study.

    ../../../venv/Scripts/python.exe -m quality_analyst.labelling.make_sheet [output folder]

Writes two files (default folder: services/agents/data/labelling, git-ignored):
  * labelling-sheet.html  what the labellers get. 50 calls, no analyst result, no expected labels inside.
  * answer-key.json       what the analyst said on each call, and our own labels where a call has them. Keep it away from the labellers.
The choice of calls is fixed by SEED, so the same sheet comes out every time. 30 calls are short hand-written cases (from the held-out test split first,
every rule appearing at least once), 20 are simulated history calls spread from the worst to the best score; they are mixed and renamed L01 to L50.
When real calls exist, replace `history_calls()` by them: nothing else changes.
"""
import json
import os
import random
import sys
import tempfile
from pathlib import Path

import advisor
from quality_analyst import engine, eval_cases as data, store

SEED = 7
SHEET = "v1"
N_CASES, N_HISTORY = 30, 20

# What each rule means for someone who has not read the code. Same meaning as the analyst's detector, in plain words.
DEFINITIONS = {
    "promise_before_check": "The advisor promises a refund, credit or outcome before saying they checked the policy or the rules.",
    "refund_over_limit": f"A refund or credit above {engine.REFUND_LIMIT_TND} TND is offered without mentioning a supervisor's approval.",
    "no_identity_check": "The advisor acts on the account (refund, cancellation, SIM change...) without first checking who the customer is.",
    "no_retention_offer": "The customer wants to cancel and the advisor processes it without first offering a plan review or an alternative.",
    "wrong_fact": "The advisor states a fact (delay, amount, rule) that contradicts the company facts.",
    "no_grounded_answer": "Nothing the advisor says answers the customer's problem the way the company facts do (vague, or off topic).",
    "overpromise": "The advisor gives an absolute guarantee ('I guarantee', '100 %', 'it will never happen again').",
    "no_empathy": "The customer is upset from the start and the advisor's first replies do not acknowledge the frustration.",
    "jargon": "The advisor uses technical terms the customer would not understand (for example provisioning, APN, TTL).",
    "ask_repeat": "The advisor asks the customer to explain the problem again, although they already did.",
    "transfer": "The advisor passes the customer to someone else without handing over the history or staying on the line.",
    "no_greeting": "The advisor's first words are not a greeting or an offer of help.",
    "no_follow_up": "No written confirmation, ticket number or follow-up (text, email, callback) is promised or given.",
    "unresolved": "The customer ends the call still upset (mood under about 40) and nothing was agreed.",
    "hang_up": "The customer hangs up.",
    "no_closing": "The advisor does not close the call (for example 'anything else I can help with?', thanks, goodbye).",
    "mood_drop": "The customer's mood falls by 15 points or more right after an advisor reply.",
    "low_mood_end": "The customer's last mood is clearly low (well under 70).",
}


def mmss(seconds):
    return f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"


def case_calls(rng):
    test = [c for c in data.CASES if c["split"] == "test"]
    chosen = {}
    for rule in engine.RULES:                         # every rule appears in at least one call, when a test case exists for it
        pool = [c for c in test if rule in c["expect"] and c["id"] not in chosen]
        if pool:
            c = rng.choice(pool)
            chosen[c["id"]] = c
    rest = [c for c in test if c["id"] not in chosen]
    rng.shuffle(rest)
    for c in rest:
        if len(chosen) >= N_CASES:
            break
        chosen[c["id"]] = c
    out = []
    for c in chosen.values():
        fired = sorted({e["rule"] for e in engine.review(c["turns"], "Eval", c["id"])["errors"]})
        turns = [dict(who=t["speaker"], text=t["text"], mood=t.get("mood")) for t in c["turns"]]
        out.append(dict(source=f"case {c['id']}", turns=turns, analyst=fired, ours=dict(expect=c["expect"], absent=c["absent"])))
    return out


def history_calls(rng):
    """The simulated history, read from a throw-away database so the real one is never touched."""
    saved = os.environ.get("QUALITY_DB")
    os.environ["QUALITY_DB"] = str(Path(tempfile.mkdtemp()) / "history.db")
    try:
        store.ensure_history()
        reviews = sorted(store.recent(1000), key=lambda r: (r["overall"], r["callId"]))
    finally:
        if saved is None:
            os.environ.pop("QUALITY_DB")
        else:
            os.environ["QUALITY_DB"] = saved
    picks = [reviews[int(i * len(reviews) / N_HISTORY)] for i in range(N_HISTORY)]
    out = []
    for r in picks:
        turns = [dict(who=t["speaker"], text=t["text"], mood=t.get("mood") if t["speaker"] == "customer" else None, time=mmss(t["start"])) for t in r["turns"]]
        out.append(dict(source=f"history {r['callId']}", turns=turns, analyst=sorted({e["rule"] for e in r["errors"]}), ours=None))
    return out


def build(folder: Path) -> tuple[Path, Path]:
    rng = random.Random(SEED)
    calls = case_calls(rng) + history_calls(rng)
    rng.shuffle(calls)
    for n, c in enumerate(calls, 1):
        c["id"] = f"L{n:02d}"
    groups = []
    for criterion in engine.CRITERIA:
        rules = [dict(id=r, label=engine.RULE_LABELS[r], **{"def": DEFINITIONS[r]}) for r, spec in engine.RULES.items() if spec["criterion"] == criterion]
        if rules:
            groups.append(dict(criterion=criterion, rules=rules))
    sheet = dict(sheet=SHEET, groups=groups, facts=[dict(title=d["title"], text=d["text"]) for d in advisor.KB],
                 calls=[dict(id=c["id"], turns=c["turns"]) for c in calls])
    key = dict(sheet=SHEET, seed=SEED, calls={c["id"]: dict(source=c["source"], analyst=c["analyst"], ours=c["ours"]) for c in calls})
    folder.mkdir(parents=True, exist_ok=True)
    template = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
    payload = json.dumps(sheet, ensure_ascii=False).replace("</", "<\\/")
    html, key_path = folder / "labelling-sheet.html", folder / "answer-key.json"
    html.write_text(template.replace("/*DATA*/", payload), encoding="utf-8")
    key_path.write_text(json.dumps(key, indent=1, ensure_ascii=False), encoding="utf-8")
    return html, key_path


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "data" / "labelling"
    for p in build(out):
        print(p)
