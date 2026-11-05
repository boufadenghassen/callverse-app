"""What happened when an advisor practised a scenario: the score, what moved against their usual level, and what to do next.

One SQLite file (services/agents/data/training.db, TRAINING_DB to move it). Each attempt keeps the advisor's averages from just before it, so the
comparison stays true later. Practice calls are scored by the real quality analyst but do not count in the advisor's quality analytics.
"""
import datetime as dt
import json
import os
import sqlite3
from pathlib import Path

from .adaptive import compare_progress
from .schemas import QAWeakness

PASS = 80          # at or above this, with nothing worse than usual, the advisor moves up a level
NEARLY = 60


def db_path() -> Path:
    return Path(os.environ.get("TRAINING_DB", Path(__file__).resolve().parents[1] / "data" / "training.db"))


def _conn() -> sqlite3.Connection:
    db_path().parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db_path())
    c.execute("create table if not exists attempts (call_id text primary key, advisor text not null, scenario_id text not null, created text not null, attempt text not null)")
    return c


def advice(overall: int, rows: list[dict], weakest: str) -> tuple[str, str]:
    """(next step, the sentence for the coach): `harder` or `replay`."""
    worse = [r["criterion"] for r in rows if r["status"] == "regressed"]
    if overall >= PASS and not worse:
        return "harder", f"Passed at {overall}/100 with nothing worse than usual: try the harder version."
    if overall >= PASS:
        return "replay", f"A good score of {overall}/100, but {', '.join(worse).lower()} fell below the advisor's usual level: replay it with that in mind."
    if overall >= NEARLY:
        return "replay", f"Nearly there at {overall}/100: replay it, focusing on {weakest.lower()}."
    return "replay", f"{overall}/100: go through the review with the advisor, then replay it, starting with {weakest.lower()}."


def record(scenario_id: str, title: str, advisor: str, review: dict, usual: dict[str, float] | None) -> dict:
    """Keep one attempt. `usual` is the advisor's average per criterion (out of 10) from before this call, or None for a first-timer."""
    after = {c["name"]: c["score"] for c in review["criteria"]}
    rows = []
    if usual:
        report = compare_progress([QAWeakness(criterion=k, score=v * 10) for k, v in usual.items()], [QAWeakness(criterion=k, score=v * 10) for k, v in after.items()])
        rows = [dict(criterion=r.criterion, before=round(r.before * 10, 1), after=round(r.after * 10, 1), status=r.status) for r in report.items]
    step, words = advice(review["overall"], rows, min(after, key=after.get))
    created = dt.datetime.now().replace(microsecond=0).isoformat()
    attempt = dict(callId=review["callId"], scenarioId=scenario_id, title=title, advisor=advisor, overall=review["overall"], date=created[:10], changes=rows, next=step, advice=words)
    with _conn() as c:
        c.execute("insert or replace into attempts values (?,?,?,?,?)", (review["callId"], advisor, scenario_id, created, json.dumps(attempt)))
    return attempt


def history(advisor: str, limit: int = 8) -> dict:
    """The advisor's attempts, newest first, and how their scores moved from the first attempt to the latest."""
    with _conn() as c:
        rows = c.execute("select attempt from attempts where advisor = ? order by created desc, call_id desc", (advisor,)).fetchall()
    attempts = [json.loads(r[0]) for r in rows]
    scores = [a["overall"] for a in attempts]
    return dict(attempts=attempts[:limit], count=len(attempts), best=max(scores, default=None), trend=scores[0] - scores[-1] if len(scores) > 1 else None)
