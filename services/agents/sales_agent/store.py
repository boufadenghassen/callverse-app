"""What happened to the offers that were made: accepted or declined. It feeds the "track record" factor and the "which offers convert" analytics.

SQLite in services/agents/data/sales.db (git-ignored; SALES_DB moves it). An empty store is filled with 240 SIMULATED offers over eight weeks, so the
analytics have something to show: in the simulation an offer is accepted more often when it is relevant and made at a good moment, which is how the
history was written, so it shows the loop works, not that real customers behave this way. Rows made by people carry source "advisor".
"""
import datetime as dt
import os
import random
import sqlite3
from pathlib import Path

from . import engine


def db_path() -> Path:
    return Path(os.environ.get("SALES_DB", Path(__file__).resolve().parents[1] / "data" / "sales.db"))


def _conn() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.execute("create table if not exists offers_log (id integer primary key autoincrement, at text, customer text, offer_id text, relevance integer, "
              "cue text, need text, outcome text, source text)")
    return c


def record(customer_id: str, offer_id: str, outcome: str, relevance: int = 0, cue: str = "now", need: str = "", source: str = "advisor", at: str | None = None) -> None:
    with _conn() as c:
        c.execute("insert into offers_log (at, customer, offer_id, relevance, cue, need, outcome, source) values (?,?,?,?,?,?,?,?)",
                  (at or dt.datetime.now().replace(microsecond=0).isoformat(), customer_id, offer_id, relevance, cue, need, outcome, source))


def count() -> int:
    with _conn() as c:
        return c.execute("select count(*) from offers_log").fetchone()[0]


def rates() -> dict[str, tuple[int, int]]:
    """offer id -> (offers made, accepted)."""
    with _conn() as c:
        rows = c.execute("select offer_id, count(*), sum(outcome = 'accepted') from offers_log group by offer_id").fetchall()
    return {r[0]: (r[1], r[2] or 0) for r in rows}


BASE = {"roaming-pass": 0.45, "data-booster": 0.35, "plan-upgrade": 0.2, "family-line": 0.3, "home-fiber": 0.25, "loyalty-discount": 0.5,
        "autopay": 0.55, "premium-care": 0.15, "device-plan": 0.2, "intl-calls": 0.3}


def ensure_history() -> None:
    """Create the simulated history once, when the store is empty."""
    if count():
        return
    rng = random.Random(11)
    ids, today = list(BASE), dt.date.today()
    for _ in range(240):
        offer = rng.choice(ids)
        relevance = rng.randint(30, 95)
        cue = "after_resolution" if rng.random() < 0.25 else "now"
        p = BASE[offer] * (1.5 if relevance >= 70 else 1.0 if relevance >= 50 else 0.6) * (1.0 if cue == "now" else 0.45)
        outcome = "accepted" if rng.random() < min(p, 0.9) else "declined"
        when = dt.datetime.combine(today - dt.timedelta(days=rng.randint(0, 55)), dt.time(rng.randint(9, 17), rng.randint(0, 59)))
        record(f"SIM-{rng.randint(1000, 9999)}", offer, outcome, relevance, cue, rng.choice(list(engine.OFFERS[offer]["needs"])), "simulated", when.isoformat())


def _row(label: str, offered: int, accepted: int, **extra) -> dict:
    return dict(label=label, offered=offered, accepted=accepted, rate=round(accepted / offered, 2) if offered else None, **extra)


def analytics() -> dict:
    with _conn() as c:
        rows = c.execute("select offer_id, relevance, cue, need, outcome, source from offers_log").fetchall()
    total, accepted = len(rows), sum(r[4] == "accepted" for r in rows)

    def group(key, labels):
        out = []
        for k, label in labels:
            mine = [r for r in rows if key(r) == k]
            if mine:
                out.append(_row(label, len(mine), sum(r[4] == "accepted" for r in mine), key=k))
        return out

    band = lambda r: "70+" if r[1] >= 70 else "50-69" if r[1] >= 50 else "under 50"      # noqa: E731
    return dict(
        total=total, accepted=accepted, rate=round(accepted / total, 2) if total else None, simulated=sum(r[5] == "simulated" for r in rows),
        byOffer=sorted(group(lambda r: r[0], [(o["id"], engine.OFFERS[o["id"]]["name"]) for o in engine.CATALOG["offers"]]), key=lambda r: -(r["rate"] or 0)),
        byRelevance=group(band, [("70+", "Relevance 70 or more"), ("50-69", "Relevance 50 to 69"), ("under 50", "Relevance under 50")]),
        byMoment=group(lambda r: r[2], [("now", "Offered at a good moment"), ("after_resolution", "Offered before the problem was solved")]),
        byNeed=sorted(group(lambda r: r[3], [(k, v["label"]) for k, v in engine.NEEDS.items()]), key=lambda r: -(r["rate"] or 0)),
        method="Each offer made is logged with its relevance, the moment and the need behind it, then marked accepted or declined. The track record factor of the "
               "ranking is the smoothed acceptance rate of the offer, worth -10 to +10 points. The history shown here is simulated: it shows the loop works, "
               "not how real customers behave.")
