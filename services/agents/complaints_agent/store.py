"""The complaint cases and everything that happens to them, in SQLite (services/agents/data/complaints.db, git-ignored; COMPLAINTS_DB moves it).

A case is the customer's words plus a status (open, taken, resolved, closed), who owns it, and a log of events. The analysis (root cause, severity,
escalation risk, deadline) is not stored: it is worked out again from the text, the customer file and the other cases every time, so a change in the
rules shows at once. Only a manual change of level (an override) is stored.

An empty store is filled with SIMULATED cases: today's open cases (the first three are the demo cases of the page) and 38 resolved ones over eight weeks,
deterministic, with roaming complaints rising in the last weeks so the trend view has something to show. Cases made by people are marked source "agent".
"""
import datetime as dt
import os
import random
import sqlite3
from collections import Counter
from pathlib import Path

from . import engine

STATUSES = ("open", "taken", "resolved", "closed")


def db_path() -> Path:
    return Path(os.environ.get("COMPLAINTS_DB", Path(__file__).resolve().parents[1] / "data" / "complaints.db"))


def _conn() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.execute("create table if not exists cases (id text primary key, customer text, summary text, text text, channel text, opened_at text, status text, assigned text, "
              "override text, sla_hours integer, level_open text, resolved_at text, resolution text, closed_at text, trusted integer, source text, call_id text)")
    c.execute("create table if not exists events (id integer primary key autoincrement, case_id text, at text, who text, kind text, note text)")
    return c


def _case(r: sqlite3.Row) -> dict:
    d = dict(r)
    for k in ("opened_at", "resolved_at", "closed_at"):
        d[k] = dt.datetime.fromisoformat(d[k]) if d[k] else None
    return d


def now() -> dt.datetime:
    return dt.datetime.now().replace(microsecond=0)


def all_cases() -> list[dict]:
    with _conn() as c:
        return [_case(r) for r in c.execute("select * from cases order by opened_at")]


def get(case_id: str) -> dict:
    with _conn() as c:
        r = c.execute("select * from cases where id = ?", (case_id,)).fetchone()
    if r is None:
        raise KeyError(case_id)
    return _case(r)


def events(case_id: str) -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute("select at, who, kind, note from events where case_id = ? order by id", (case_id,))]


def _log(c: sqlite3.Connection, case_id: str, at: dt.datetime, who: str, kind: str, note: str = "") -> None:
    c.execute("insert into events (case_id, at, who, kind, note) values (?,?,?,?,?)", (case_id, at.isoformat(timespec="minutes"), who, kind, note))


def alerted(case_id: str) -> bool:
    with _conn() as c:
        return c.execute("select 1 from events where case_id = ? and kind = 'alert'", (case_id,)).fetchone() is not None


def _next_id(c: sqlite3.Connection) -> str:
    row = c.execute("select max(cast(substr(id, 5) as integer)) from cases").fetchone()
    return f"CMP-{max(int(row[0] or 0), 227) + 1}"


def create(text: str, customer: str | None = None, channel: str = "call", source: str = "agent", at: dt.datetime | None = None, case_id: str | None = None,
           call_id: str | None = None, who: str = "system") -> dict:
    """Open a case. Its level and deadline are worked out now and kept (`level_open`, `sla_hours`)."""
    at = at or now()
    with _conn() as c:
        case_id = case_id or _next_id(c)
        row = dict(id=case_id, customer=customer, summary=engine.short(text), text=text, channel=channel, opened_at=at, status="open", assigned=None, override=None,
                   sla_hours=0, level_open="", resolved_at=None, resolution=None, closed_at=None, trusted=None, source=source, call_id=call_id)
        a = engine.analyse(row, [x for x in (_case(r) for r in c.execute("select * from cases"))], at)
        row.update(level_open=a["severity"], sla_hours=engine.sla_hours(a["severity"]))
        c.execute("insert into cases values (:id,:customer,:summary,:text,:channel,:opened_at,:status,:assigned,:override,:sla_hours,:level_open,:resolved_at,:resolution,"
                  ":closed_at,:trusted,:source,:call_id)", dict(row, opened_at=at.isoformat(timespec="minutes")))
        _log(c, case_id, at, who, "opened", f"{channel}, {source}")
    return row


def act(case_id: str, action: str, by: str, note: str = "", at: dt.datetime | None = None, resolution: str | None = None, level: str | None = None,
        trusted: bool | None = None) -> dict:
    """take, escalate, severity, alert, resolve, close or reopen a case. A wrong move (resolving a closed case...) is a ValueError."""
    at = at or now()
    c = get(case_id)
    with _conn() as db:
        if action == "take":
            if c["status"] not in ("open", "taken"):
                raise ValueError("Only an open case can be taken.")
            db.execute("update cases set status = 'taken', assigned = ? where id = ?", (by, case_id))
            _log(db, case_id, at, by, "taken", note)
        elif action in ("escalate", "severity"):
            if c["status"] not in ("open", "taken"):
                raise ValueError("Only an open case can be escalated.")
            current = engine.analyse(c, all_cases(), at)["severity"]
            if action == "severity":
                if level not in engine.LEVELS:
                    raise ValueError("Choose a level: " + ", ".join(engine.ORDER) + ".")
                target = level
            else:
                i = engine.ORDER.index(current)
                target = engine.ORDER[max(0, i - 1)]
            if target != current:
                db.execute("update cases set override = ? where id = ?", (target, case_id))
            _log(db, case_id, at, by, "escalated" if action == "escalate" else "level set", f"{current} to {target}" + (f": {note}" if note else ""))
        elif action == "alert":
            if c["status"] not in ("open", "taken"):
                raise ValueError("Only an open case needs an alert.")
            _log(db, case_id, at, by, "alert", note or "supervisor alerted")
        elif action == "resolve":
            if c["status"] not in ("open", "taken"):
                raise ValueError("Only an open case can be resolved.")
            if resolution not in engine.RESOLUTIONS:
                raise ValueError("Choose how it was resolved.")
            db.execute("update cases set status = 'resolved', resolved_at = ?, resolution = ?, assigned = coalesce(assigned, ?) where id = ?", (at.isoformat(timespec="minutes"), resolution, by, case_id))
            _log(db, case_id, at, by, "resolved", f"{engine.RESOLUTIONS[resolution]}" + (f": {note}" if note else ""))
        elif action == "close":
            if c["status"] != "resolved":
                raise ValueError("Only a resolved case can be closed after the follow-up.")
            if trusted is None:
                raise ValueError("Say whether the customer trusts us again.")
            if trusted:
                db.execute("update cases set status = 'closed', closed_at = ?, trusted = 1 where id = ?", (at.isoformat(timespec="minutes"), case_id))
                _log(db, case_id, at, by, "closed", "the customer is satisfied" + (f": {note}" if note else ""))
            else:
                db.execute("update cases set status = 'open', resolved_at = null, resolution = null, closed_at = null, trusted = 0, override = null where id = ?", (case_id,))
                _log(db, case_id, at, by, "reopened", "trust not restored" + (f": {note}" if note else ""))
        elif action == "reopen":
            if c["status"] not in ("resolved", "closed"):
                raise ValueError("Only a resolved or closed case can be reopened.")
            db.execute("update cases set status = 'open', resolved_at = null, resolution = null, closed_at = null, trusted = null where id = ?", (case_id,))
            _log(db, case_id, at, by, "reopened", note)
        else:
            raise ValueError("Unknown action.")
    return get(case_id)


def _set_trust(case_id: str, value: int) -> None:
    with _conn() as db:
        db.execute("update cases set trusted = ? where id = ?", (value, case_id))


def analysed(at: dt.datetime | None = None, status: tuple[str, ...] | None = None) -> list[dict]:
    """The analysis of every case (or of the cases in these statuses), most dangerous first."""
    at = at or now()
    cases = all_cases()
    out = []
    for c in cases:
        if status and c["status"] not in status:
            continue
        c["alerted"] = alerted(c["id"])
        out.append(engine.analyse(c, cases, at))
    return sorted(out, key=lambda a: (-a["escalationRisk"], a["hoursLeft"]))


def detail(case_id: str, at: dt.datetime | None = None) -> dict:
    """One case in full: the analysis, the customer's history with us, the log, and what worked on similar cases."""
    at = at or now()
    c = get(case_id)
    cases = all_cases()
    c["alerted"] = alerted(case_id)
    a = engine.analyse(c, cases, at)
    resolved = [x for x in cases if x["id"] != case_id and x["status"] in ("resolved", "closed") and engine.classify(x["text"])[0] == a["clusterKey"]]
    codes = Counter(x["resolution"] for x in resolved if x["resolution"])
    worked = None
    if codes:
        code, n = codes.most_common(1)[0]
        worked = dict(code=code, label=engine.RESOLUTIONS[code], count=n, of=len(resolved))
    earlier = [dict(id=x["id"], summary=x["summary"], opened=x["opened_at"].isoformat(timespec="minutes"), status=x["status"])
               for x in cases if x["id"] != case_id and c["customer"] and x["customer"] == c["customer"]][-5:]
    return dict(a, text=c["text"], events=events(case_id), earlier=earlier, similar=[dict(id=x["id"], summary=x["summary"], resolution=engine.RESOLUTIONS.get(x["resolution"], ""))
                                                                                    for x in resolved[-3:]][::-1], worked=worked,
                resolution=engine.RESOLUTIONS.get(c["resolution"]) if c["resolution"] else None, trusted=c["trusted"], callId=c["call_id"],
                customerFile=_customer_file(c["customer"]))


def _customer_file(customer_id: str | None) -> dict | None:
    if not customer_id:
        return None
    c = engine.advisor.get_customer(customer_id)
    if not c:
        return None
    p = engine.sales.PROFILES.get(customer_id, {})
    return dict(id=c["id"], name=c["name"], profile=c["profile"], contract=c["contract"], openTickets=c["openTickets"], transfers=c["transfers"], mood=c["mood"],
                tenureYears=p.get("tenureYears"), monthlyTnd=p.get("monthlyTnd"), usageTrend=p.get("usageTrend"))


def follow_ups(at: dt.datetime | None = None) -> list[dict]:
    """Resolved cases waiting for the check that the customer trusts us again, with the time that check is due."""
    at = at or now()
    out = []
    for c in all_cases():
        if c["status"] == "resolved":
            due = c["resolved_at"] + dt.timedelta(hours=engine.FOLLOW_UP_HOURS)
            out.append(dict(id=c["id"], summary=c["summary"], customer=c["customer"], resolution=engine.RESOLUTIONS.get(c["resolution"], ""), due=due.isoformat(timespec="minutes"),
                            dueInHours=round((due - at).total_seconds() / 3600, 1)))
    return sorted(out, key=lambda f: f["dueInHours"])


def _avg(xs):
    xs = list(xs)
    return round(sum(xs) / len(xs), 1) if xs else None


def insights(at: dt.datetime | None = None) -> dict:
    at = at or now()
    cases = all_cases()
    live = analysed(at, ("open", "taken"))
    done = [c for c in cases if c["status"] in ("resolved", "closed") and c["resolved_at"]]
    by_level = {lv: sum(1 for a in live if a["severity"] == lv) for lv in engine.ORDER}
    recent, before = at - dt.timedelta(days=28), at - dt.timedelta(days=56)

    def cluster_of(c):
        return engine.classify(c["text"])[0]

    rows = []
    for key in list(engine.CLUSTERS) + ["other"]:
        mine = [c for c in cases if cluster_of(c) == key]
        if not mine:
            continue
        now_n = sum(1 for c in mine if c["opened_at"] >= recent)
        prev_n = sum(1 for c in mine if before <= c["opened_at"] < recent)
        solved = [c for c in mine if c in done]
        codes = Counter(c["resolution"] for c in solved if c["resolution"])
        top = codes.most_common(1)
        info = engine.cluster_info(key)
        rows.append(dict(key=key, label=info["label"], cause=info["cause"], open=sum(1 for a in live if a["clusterKey"] == key), last28=now_n, previous28=prev_n, trend=now_n - prev_n,
                         avgHours=_avg((c["resolved_at"] - c["opened_at"]).total_seconds() / 3600 for c in solved),
                         worked=dict(label=engine.RESOLUTIONS[top[0][0]], count=top[0][1], of=len(solved)) if top else None))
    rows.sort(key=lambda r: (-r["last28"], r["label"]))
    weeks = []
    for w in range(7, -1, -1):
        lo, hi = at - dt.timedelta(days=7 * (w + 1)), at - dt.timedelta(days=7 * w)
        weeks.append(sum(1 for c in cases if lo <= c["opened_at"] < hi))
    met = [((c["resolved_at"] - c["opened_at"]).total_seconds() / 3600) <= c["sla_hours"] for c in done]
    closed = [c for c in cases if c["status"] == "closed"]
    reopened = sum(1 for c in cases if c["trusted"] == 0)
    known = [c for c in cases if c["customer"] and c["opened_at"] >= before]
    repeat = [c for c in known if engine.contacts_of(c, cases, at) >= 1]
    causes = Counter(engine.cluster_info(cluster_of(c))["cause"] for c in cases)
    total = sum(causes.values()) or 1
    return dict(
        open=len(live), byLevel=by_level, avgRisk=round(sum(a["escalationRisk"] for a in live) / len(live)) if live else 0,
        overdue=sum(1 for a in live if a["deadline"]["overdue"]), warnings=sum(1 for a in live if a["warning"]), followUps=len(follow_ups(at)),
        resolved=len(done), avgResolutionHours=_avg((c["resolved_at"] - c["opened_at"]).total_seconds() / 3600 for c in done),
        slaMetRate=round(sum(met) / len(met), 2) if met else None, trustRate=round(sum(1 for c in closed if c["trusted"]) / len(closed), 2) if closed else None,
        reopened=reopened, repeatRate=round(len(repeat) / len(known), 2) if known else None, weeks=weeks, clusters=rows,
        causes=[dict(cause=k, cases=n, share=round(n / total, 2)) for k, n in causes.most_common()], simulated=sum(1 for c in cases if c["source"] == "simulated"),
        method="Every case is read by the rules of the complaint agent (root cause from phrases, severity and escalation risk as sums of named factors, deadline from the level). "
               "Trends compare the last 28 days with the 28 before. The history is simulated: it shows the views work, not how real customers complain.")


# ---- the simulated history
OPEN_CASES = [
    # id, customer, text, hours ago, status, who
    ("CMP-221", "YT-1042", "I was charged twice for 180 dinars on my September bill and this is the third time I contact you about it. This is unacceptable, I will post this online and cancel my contract.", 9, "open", None),
    ("CMP-219", "IK-2210", "My roaming bundle did not work abroad last week, I had no signal in Italy for four days and I still have not been refunded.", 5, "taken", "amine"),
    ("CMP-214", "WF-3391", "The cancellation fee of 90 dinars makes no sense, nobody explained it when I signed. I want to cancel my contract.", 3, "open", None),
    ("CMP-223", "SH-5520", "My internet has been slow for weeks, it is a scandal. The whole building has the same problem and I am looking at other operators.", 20, "open", None),
    ("CMP-224", "MS-0007", "My data ran out in two days, I think the usage is wrong.", 2, "open", None),
    ("CMP-225", None, "An advisor was rude to me and hung up on me. I will go to the consumer protection association if nobody calls me back.", 30, "taken", "sami"),
]
OLDER = [   # earlier contacts of the customer behind CMP-221, so that "third time" is true
    ("CMP-190", "YT-1042", "I was charged twice on my August bill for 42 dinars.", 24 * 20, "resolved", "refunded"),
    ("CMP-205", "YT-1042", "Duplicate charge again on a top-up of 15 dinars.", 24 * 8, "resolved", "refunded"),
]
TEMPLATES = {
    "billing_duplicate": ["I was charged twice for {a} dinars this month.", "There is a double charge of {a} TND on my bill and nobody answers.", "A duplicate payment of {a} dinars left my account."],
    "billing_amount": ["My bill is too high, {a} dinars instead of the usual amount.", "The invoice is wrong, I never agreed to this price increase.", "I was overcharged {a} TND and I want it explained."],
    "roaming": ["My roaming pass did not work abroad and I had no signal for days.", "Roaming bundle not activated in Turkey, I paid {a} dinars for nothing.", "No signal abroad although I bought the roaming pass."],
    "contract_terms": ["The cancellation fee of {a} dinars is unfair, I was not told about the commitment.", "I am locked in a contract I did not understand and the penalty is {a} TND."],
    "network": ["Slow internet at home for two weeks, it keeps disconnecting.", "No signal in my street since Monday, dropped calls all day.", "There is an outage in our area and nobody tells us when it will end."],
    "data_usage": ["My data ran out in three days, the usage looks wrong.", "I used all my data but I hardly use my phone, please check."],
    "repeat_contact": ["This is the third time I call about the same problem and nobody called back.", "Still no answer after a promised call back, this is the second time I write."],
    "conduct": ["The advisor was rude and I was transferred twice.", "Nobody listened to me, the advisor hung up on me."],
    "device": ["My new phone was never delivered although I paid {a} dinars.", "The replacement SIM still has not arrived."],
}
RESOLUTION_BY_CLUSTER = {k: v["resolutions"] for k, v in engine.CLUSTERS.items()}


def ensure_history(at: dt.datetime | None = None) -> None:
    """Fill an empty store: today's open cases and the simulated history. Done once."""
    with _conn() as c:
        if c.execute("select count(*) from cases").fetchone()[0]:
            return
    at = at or now()
    rng = random.Random(19)
    for cid, customer, text, days, status, resolution in OLDER:
        opened = at - dt.timedelta(hours=days)
        create(text, customer, "call", "simulated", opened, cid, who="system")
        act(cid, "resolve", "amine", "", opened + dt.timedelta(hours=10), resolution)
        act(cid, "close", "amine", "", opened + dt.timedelta(hours=10 + engine.FOLLOW_UP_HOURS), trusted=True)
    customers = [None, "YT-1042", "MS-0007", "IK-2210", "WF-3391", "SH-5520"]
    keys = list(TEMPLATES)
    for n in range(38):
        age_days = rng.uniform(1, 56)
        # roaming complaints rise in the last three weeks
        key = "roaming" if age_days < 21 and rng.random() < 0.4 else rng.choice(keys)
        text = rng.choice(TEMPLATES[key]).format(a=rng.choice([20, 35, 60, 90, 140, 220, 320]))
        opened = at - dt.timedelta(days=age_days)
        cid = f"CMP-{100 + n}"
        row = create(text, rng.choice(customers) if rng.random() < 0.5 else None, rng.choice(["call", "call", "email", "chat"]), "simulated", opened, cid, who="system")
        sla = row["sla_hours"]
        who = rng.choice(["amine", "sami", "hela"])
        act(cid, "take", who, "", opened + dt.timedelta(hours=min(sla * 0.1, 3)))
        done = opened + dt.timedelta(hours=sla * rng.uniform(0.3, 1.4))
        if done >= at - dt.timedelta(hours=2):
            done = opened + (at - opened) * 0.8                            # the history is all resolved: today's open cases are the six below
        act(cid, "resolve", who, "", done, rng.choice(RESOLUTION_BY_CLUSTER.get(engine.classify(text)[0], ["explained"])))
        check = done + dt.timedelta(hours=engine.FOLLOW_UP_HOURS)
        if check < at:                                                     # the follow-up call already happened
            act(cid, "close", who, "", check, trusted=True)
            if rng.random() > 0.85:
                _set_trust(cid, 0)                                         # a customer who was still unhappy at the follow-up
    for cid, customer, text, hours, status, who in OPEN_CASES:
        opened = at - dt.timedelta(hours=hours)
        create(text, customer, "call", "simulated", opened, cid, who="system")
        if status == "taken":
            act(cid, "take", who, "", opened + dt.timedelta(minutes=30))
