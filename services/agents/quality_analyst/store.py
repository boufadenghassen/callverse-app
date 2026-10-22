"""Where reviewed calls are kept (SQLite, one file) and the analytics computed from them: per advisor and for the team.

The file lives in services/agents/data/ (git-ignored). On a first run with an empty store a synthetic history of past calls is created
by seed.py, so the analytics have something to show; the calls are simulated but every one is scored by the real engine.review().
"""
import datetime as dt
import json
import os
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from . import engine as q

FIRST_ID = 3300


def db_path() -> Path:
    """Read each time, so a test (or another deployment) can point the store somewhere else with QUALITY_DB."""
    return Path(os.environ.get("QUALITY_DB", Path(__file__).resolve().parents[1] / "data" / "quality.db"))


def _conn() -> sqlite3.Connection:
    db_path().parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db_path())
    c.execute("create table if not exists calls (call_id text primary key, advisor text not null, source text, created text not null, intent text, overall integer, review text not null)")
    c.execute("create index if not exists calls_advisor on calls(advisor)")
    c.execute("create table if not exists feedback (call_id text not null, rule text not null, turn integer not null, verdict text not null, by text, created text, primary key (call_id, rule, turn))")
    return c


def next_call_id() -> str:
    with _conn() as c:
        rows = [int(r[0][5:]) for r in c.execute("select call_id from calls") if r[0][5:].isdigit()]
    return f"CALL-{max(rows, default=FIRST_ID - 1) + 1}"


def save(review: dict, created: str | None = None) -> dict:
    created = created or dt.datetime.now().replace(microsecond=0).isoformat()
    review["date"] = created[:10]
    with _conn() as c:
        c.execute("insert or replace into calls values (?,?,?,?,?,?,?)", (review["callId"], review["advisor"], review["source"], created, review["intent"], review["overall"], json.dumps(review)))
    return review


def set_feedback(call_id: str, rule: str, turn: int, verdict: str, by: str) -> None:
    """A human's verdict on one finding: 'agree' (it is an error) or 'disagree' (it is not); 'clear' removes the verdict."""
    with _conn() as c:
        if verdict == "clear":
            c.execute("delete from feedback where call_id = ? and rule = ? and turn = ?", (call_id, rule, turn))
        else:
            c.execute("insert or replace into feedback values (?,?,?,?,?,?)", (call_id, rule, turn, verdict, by, dt.datetime.now().replace(microsecond=0).isoformat()))


def _feedback(call_ids: list[str] | None = None) -> dict[str, dict[tuple[str, int], str]]:
    with _conn() as c:
        rows = c.execute("select call_id, rule, turn, verdict from feedback").fetchall()
    out: dict[str, dict[tuple[str, int], str]] = {}
    for cid, rule, turn, verdict in rows:
        if call_ids is None or cid in call_ids:
            out.setdefault(cid, {})[(rule, turn)] = verdict
    return out


def _adjusted(review: dict, fb: dict[tuple[str, int], str] | None) -> dict:
    """The stored review as the human reviewer left it: each finding shows its verdict, and disputed findings no longer count."""
    review = dict(review)
    if fb:
        review["errors"] = [dict(e, verdict=fb.get((e["rule"], e["turn"]))) for e in review["errors"]]
    disputed = _disputed(fb)
    return q.rescore(review, disputed, with_drivers=False) if disputed else review


def _disputed(fb) -> set[tuple[str, int]]:
    return {k for k, v in (fb or {}).items() if v == "disagree"}


def _shown(review: dict, fb) -> dict:
    """A review ready to show: with what moved its score. The explanation costs a few re-scorings per call, so only the calls shown get it
    (the analytics never do); reviews stored before it existed, and reviews a reviewer has disputed, get it worked out now."""
    disputed = _disputed(fb)
    return q.explained(review, disputed) if disputed or "drivers" not in review else review


def get(call_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute("select review from calls where call_id = ?", (call_id,)).fetchone()
    if not row:
        return None
    fb = _feedback([call_id]).get(call_id)
    return _shown(_adjusted(json.loads(row[0]), fb), fb)


def recent(limit: int = 20, advisor: str | None = None, rule: str | None = None, below: int | None = None) -> list[dict]:
    """The latest reviews, newest first, as the human reviewer left them. Filters: one advisor, calls where a rule fired, calls scoring below a number."""
    sql, args = "select review from calls", []
    if advisor:
        sql, args = sql + " where advisor = ?", [advisor]
    with _conn() as c:
        rows = c.execute(sql + " order by created desc, call_id desc" + ("" if rule or below else " limit ?"), args + ([] if rule or below else [limit])).fetchall()
    reviews = [json.loads(r[0]) for r in rows]
    fb = _feedback([r["callId"] for r in reviews])
    reviews = [_adjusted(r, fb.get(r["callId"])) for r in reviews]
    if rule:
        reviews = [r for r in reviews if any(e["rule"] == rule and e.get("verdict") != "disagree" for e in r["errors"])]
    if below:
        reviews = [r for r in reviews if r["overall"] < below]
    return [_shown(r, fb.get(r["callId"])) for r in reviews[:limit]]


def count() -> int:
    with _conn() as c:
        return c.execute("select count(*) from calls").fetchone()[0]


def _rows() -> list[tuple[str, str, dict]]:
    with _conn() as c:
        rows = [(r[0], r[1], json.loads(r[2])) for r in c.execute("select created, advisor, review from calls order by created")]
    fb = _feedback()
    return [(created, advisor, _adjusted(review, fb.get(review["callId"]))) for created, advisor, review in rows]       # the analytics use the human-checked scores


def ensure_history() -> None:
    """Create the synthetic history once, when the store is empty."""
    if count() == 0:
        from . import seed
        seed.build()


# ---- analytics ---------------------------------------------------------------------------------------
WEEKS = 8


def _avg(xs) -> float | None:
    xs = list(xs)
    return round(sum(xs) / len(xs), 1) if xs else None


def _week(created: str, today: dt.date) -> int:
    """0 = this week ... 7 = seven weeks ago."""
    return min(WEEKS - 1, max(0, (today - dt.date.fromisoformat(created[:10])).days // 7))


def agreement() -> dict:
    """How often the human reviewer agrees with the analyst's findings, overall and per rule (only findings somebody looked at count)."""
    fb = _feedback()
    per: dict[str, list[int]] = {}
    for verdicts in fb.values():
        for (rule, _turn), v in verdicts.items():
            per.setdefault(rule, [0, 0])[0 if v == "agree" else 1] += 1
    agree, disagree = sum(a for a, _ in per.values()), sum(d for _, d in per.values())
    return dict(judged=agree + disagree, agree=agree, disagree=disagree, rate=round(agree / (agree + disagree), 2) if agree + disagree else None,
                byRule=sorted((dict(rule=r, label=q.RULE_LABELS[r], agree=a, disagree=d) for r, (a, d) in per.items()), key=lambda x: -x["disagree"]))


def analytics(today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    rows = _rows()
    reviews = [r for _, _, r in rows]
    if not reviews:
        return dict(team=None, advisors=[], agreement=agreement(), rules=[dict(rule=r, label=q.RULE_LABELS[r]) for r in q.RULES], method=METHOD)
    team_avg = _avg(r["overall"] for r in reviews)

    def by_criterion(rs):
        return {c: _avg(next(x["score"] for x in r["criteria"] if x["name"] == c) for r in rs) for c in q.CRITERIA}

    def top_errors(rs, n=5):
        cnt = Counter(e["rule"] for r in rs for e in {e["rule"]: e for e in r["errors"]}.values())
        return [dict(rule=rule, label=q.RULE_LABELS[rule], calls=k, share=round(k / len(rs), 2), cause=q.RULES[rule]["cause"]) for rule, k in cnt.most_common(n)]

    def weekly(rs_with_dates):
        buckets = defaultdict(list)
        for created, r in rs_with_dates:
            buckets[_week(created, today)].append(r["overall"])
        return [_avg(buckets[w]) for w in range(WEEKS - 1, -1, -1)]          # oldest first

    causes = Counter(q.RULES[e["rule"]]["cause"] for r in reviews for e in {e["rule"]: e for e in r["errors"]}.values())
    total_causes = sum(causes.values()) or 1
    intents = defaultdict(list)
    for r in reviews:
        intents[r["intent"]].append(r["overall"])
    team = dict(
        calls=len(reviews), avgOverall=team_avg, avgByCriterion=by_criterion(reviews), weeks=weekly([(c, r) for c, _, r in rows]), topErrors=top_errors(reviews, 6),
        causes=[dict(cause=c, calls=k, share=round(k / total_causes, 2)) for c, k in causes.most_common()],
        byIntent=sorted((dict(intent=i, calls=len(v), avg=_avg(v)) for i, v in intents.items()), key=lambda x: x["avg"]),
    )
    advisors = []
    for name in sorted({a for _, a, _ in rows}):
        mine = [(c, r) for c, a, r in rows if a == name]
        rs = [r for _, r in mine]
        crit = by_criterion(rs)
        weeks = weekly(mine)
        early, late = _avg(w for w in weeks[:4] if w is not None), _avg(w for w in weeks[4:] if w is not None)
        errs = top_errors(rs, 3)
        coaching = [dict(rule=e["rule"], label=e["label"], calls=e["calls"], tip=q.RULES[e["rule"]]["tip"], scenario=q.RULES[e["rule"]]["scenario"]) for e in errs[:2]]
        weakest = min(crit.items(), key=lambda kv: kv[1])
        strongest = max(crit.items(), key=lambda kv: kv[1])
        advisors.append(dict(
            advisor=name, calls=len(rs), avgOverall=_avg(r["overall"] for r in rs), vsTeam=round(_avg(r["overall"] for r in rs) - team_avg, 1), avgByCriterion=crit, weeks=weeks,
            trend=None if early is None or late is None else round(late - early, 1), weakest=dict(criterion=weakest[0], avg=weakest[1]),
            strongest=dict(criterion=strongest[0], avg=strongest[1]), topErrors=errs, coaching=coaching, lastCalls=[r["callId"] for r in rs[-3:]][::-1],
        ))
    advisors.sort(key=lambda a: a["avgOverall"])
    return dict(team=team, advisors=advisors, agreement=agreement(), rules=[dict(rule=r, label=q.RULE_LABELS[r]) for r in q.RULES], method=METHOD)


METHOD = ("Every call is scored by the rule-based quality analyst; the averages here are over the stored calls. Root cause = the kind of rule that fired "
          "(process skipped, knowledge gap, soft skills, tools). The history is simulated: advisors with different habits talked to the customer simulator, and each call was scored like a real one.")
