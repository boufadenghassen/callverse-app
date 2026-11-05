"""Complaint manager agent: triages open complaints, warns early, and shows the recurring root causes.

Data: the public Comcast consumer complaints dataset (a real telecom operator, ~2,200 complaints, 2015). It has a short complaint
text, the channel, the state, a real status (Open, Pending, Solved, Closed) and whether someone files on behalf of another person.
Put the file at datasets/complaints/raw/Comcast.csv (not in git) or set CALLVERSE_COMPLAINTS_CSV. Without it the agent falls back to
knowledge/comcast_sample.csv (20 real rows, enough for the tests).

Every number is explainable, nothing is a black box:
  * Triage: a risk score 0-100 = a base + points for signals found in the text (legal wording, money, outage, repeated problem, churn
    threat, company failure) + status + deadline. The reply lists the reasons, so Amine can check why a case ranks where it does.
    The risk has NO ground-truth label: it is a rule-based priority, not a probability. Say so in the report.
  * Deadline: the dataset is from 2015, so the hours left are SIMULATED (SLA of 48 h minus a deterministic pseudo age per ticket).
    load_cases() is the one place to plug a real ticket system and real due dates in.
  * Root causes: a readable topic taxonomy (keyword rules) for the label, plus the most characteristic words of each topic (TF-IDF),
    the monthly volume and the states where it is most common (hotspots). discover() also runs an unsupervised clustering (k-means)
    as a cross-check of the taxonomy.
"""
import hashlib
import os
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

STOP = list(ENGLISH_STOP_WORDS | {"comcast", "service", "internet", "xfinity"})   # words every complaint contains say nothing

HERE = Path(__file__).parent
DATA = Path(os.environ.get("CALLVERSE_COMPLAINTS_CSV", HERE.parents[1] / "datasets" / "complaints" / "raw" / "Comcast.csv"))
SAMPLE = HERE / "knowledge" / "comcast_sample.csv"

SLA_HOURS = 48
OPEN_STATUSES = {"open", "pending"}
CRITICAL, HIGH = 80, 50          # risk thresholds for the severity lanes (tune them with: python complaints.py)
EARLY_WARNING_RISK = 65
BASE = 15

# (name, pattern, points, reason shown to the manager)
SIGNALS = [
    ("legal", r"\b(fcc|attorney|lawsuit|sue|suing|legal|bbb|class action|violat\w*|illegal|unlawful|discriminat\w*|deceptive|fraud\w*|scam\w*|false advertis\w*)\b", 25, "Legal or regulatory wording"),
    ("money", r"\b(refund\w*|overcharg\w*|charg\w*|double|twice|owes?|collections?|fees?|billed|billing|bills?|prices?|pricing|\$\s?\d+)", 15, "Money is at stake"),
    ("outage", r"\b(outages?|no service|disconnect\w*|not working|down|offline|no internet|drops?|dropping|intermittent)\b", 12, "Service is down"),
    ("repeat", r"\b(again|still|third|fourth|multiple|several|every (day|night|week)|for (weeks|months|years)|months|weeks|repeated\w*|continu\w*|constantly)\b", 15, "Repeated or long-lasting problem"),
    ("churn", r"\b(cancel\w*|switch\w*|leav\w*|terminat\w*|competitor\w*|never again|worst)\b", 12, "Customer may leave"),
    ("failure", r"\b(refus\w*|unable|no one|nobody|rude|hung up|no response|ignor\w*|not available|runaround)\b", 10, "The company failed the customer"),
]
SIGNAL_RX = [(n, re.compile(p, re.I), pts, why) for n, p, pts, why in SIGNALS]

# root-cause taxonomy; on a tie the first topic wins, so the order matters
TOPICS = [
    ("Data caps and throttling", r"\b(data cap\w*|usage cap\w*|caps?|throttl\w*|overage\w*|data limits?|\d+\s?gb|bandwidth)\b"),
    ("Billing and fees", r"\b(bills?|billing|billed|charg\w*|fees?|refund\w*|payments?|overcharg\w*|owes?|prices?|pricing|cost\w*|rates?|promotion\w*|collections?)\b"),
    ("Speed and performance", r"\b(speeds?|slow\w*|mbps|latency|buffering|performance)\b"),
    ("Outages and disconnections", r"\b(outages?|disconnect\w*|no service|not working|down|drops?|dropping|intermittent|restore\w*|offline|availab\w*)\b"),
    ("Contract and cancellation", r"\b(cancel\w*|contracts?|terminat\w*|equipment|return\w*|early termination)\b"),
    ("Customer service", r"\b(refus\w*|rude|representatives?|customer service|technicians?|appointments?|support|help|no one|nobody)\b"),
    ("Net neutrality and regulation", r"\b(open internet|net neutrality|block\w*|fcc|monopol\w*|competition|violat\w*)\b"),
]
TOPIC_RX = [(n, re.compile(p, re.I)) for n, p in TOPICS]
OTHER = "Other"

# in-memory manager actions (a restart resets them, like the live calls)
_actions: dict[str, dict] = {}


def _clean(text) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def topic_of(text: str) -> str:
    hits = [(len(rx.findall(text)), -i, name) for i, (name, rx) in enumerate(TOPIC_RX)]
    best = max(hits)
    return best[2] if best[0] > 0 else OTHER


def _pseudo_age_hours(ticket: str) -> int:
    """Deterministic stand-in for 'how long the case has been waiting' (0-59 h), because the real dates are from 2015."""
    return int(hashlib.md5(ticket.encode()).hexdigest(), 16) % 60


@lru_cache(maxsize=1)
def load_cases() -> pd.DataFrame:
    """All complaints, one row each. The one place to plug in the real ticket system."""
    path = DATA if DATA.exists() else SAMPLE
    df = pd.read_csv(path, dtype=str).fillna("")
    df = df.rename(columns={"Ticket #": "ticket", "Customer Complaint": "text", "Received Via": "channel", "State": "state",
                            "Status": "status", "Filing on Behalf of Someone": "proxy", "Date": "date"})
    df = df[df["text"].str.strip() != ""].drop_duplicates("ticket")
    df["text"] = df["text"].map(_clean)
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%y", errors="coerce")
    df["topic"] = df["text"].map(topic_of)
    df["source"] = "Comcast.csv" if path == DATA else "comcast_sample.csv"
    return df.reset_index(drop=True)


def score(row) -> tuple[int, list[str]]:
    """Risk 0-100 and the reasons behind it."""
    pts, reasons = BASE, []
    for _name, rx, p, why in SIGNAL_RX:
        if rx.search(row["text"]):
            pts += p
            reasons.append(f"{why} (+{p})")
    if str(row["status"]).lower() == "pending":
        pts += 8
        reasons.append("Pending, no progress (+8)")
    if str(row["proxy"]).lower() == "yes":
        pts += 8
        reasons.append("Filed on behalf of someone else (+8)")
    left = SLA_HOURS - _pseudo_age_hours(row["ticket"])
    if left <= 0:
        pts += 25
        reasons.append("Deadline passed (+25)")
    elif left <= 12:
        pts += 15
        reasons.append(f"Only {left} h left (+15)")
    elif left <= 24:
        pts += 8
        reasons.append(f"{left} h left (+8)")
    return min(pts, 100), reasons


def _severity(risk: int) -> str:
    return "Critical" if risk >= CRITICAL else "High" if risk >= HIGH else "Medium"


_LANES = ["Medium", "High", "Critical"]


def _case(row) -> dict:
    risk, reasons = score(row)
    cid = f"CMP-{row['ticket']}"
    sev = _severity(risk)
    act = _actions.get(cid, {})
    for _ in range(act.get("escalations", 0)):
        sev = _LANES[min(_LANES.index(sev) + 1, 2)]
    left = SLA_HOURS - _pseudo_age_hours(row["ticket"])
    return dict(
        id=cid, summary=row["text"], severity=sev, escalationRisk=risk, cluster=row["topic"], hoursLeft=max(left, 0),
        overdue=left <= 0, reasons=reasons, status=row["status"], channel=row["channel"], state=row["state"],
        onBehalf=str(row["proxy"]).lower() == "yes", owner=act.get("owner"), route=route(sev, row["topic"]),
    )


def route(severity: str, topic: str) -> str:
    """Where the case goes: a rule over severity and root cause."""
    if severity == "Critical":
        return "Supervisor, immediately"
    if topic == "Net neutrality and regulation":
        return "Compliance desk"
    if topic in ("Billing and fees", "Contract and cancellation"):
        return "Billing disputes team"
    if topic in ("Outages and disconnections", "Speed and performance", "Data caps and throttling"):
        return "Technical escalation"
    return "Complaints team"


def open_cases(limit: int = 30) -> list[dict]:
    df = load_cases()
    df = df[df["status"].str.lower().isin(OPEN_STATUSES)]
    cases = sorted((_case(r) for _, r in df.iterrows()), key=lambda c: (-c["escalationRisk"], c["hoursLeft"], c["id"]))
    return cases[:limit]


def get_case(case_id: str) -> dict | None:
    m = re.fullmatch(r"CMP-(.+)", case_id)
    if not m:
        return None
    df = load_cases()
    rows = df[df["ticket"] == m.group(1)]
    if rows.empty:
        return None
    case = _case(rows.iloc[0])
    topic_rows = df[df["topic"] == case["cluster"]]
    case["similar"] = [dict(id=f"CMP-{r['ticket']}", summary=r["text"], status=r["status"])
                       for _, r in topic_rows[topic_rows["ticket"] != m.group(1)].head(3).iterrows()]
    return case


def assign(case_id: str, owner: str) -> dict | None:
    if get_case(case_id) is None:
        return None
    _actions.setdefault(case_id, {})["owner"] = owner
    return get_case(case_id)


def escalate(case_id: str) -> dict | None:
    if get_case(case_id) is None:
        return None
    act = _actions.setdefault(case_id, {})
    act["escalations"] = min(act.get("escalations", 0) + 1, 2)
    return get_case(case_id)


def early_warnings() -> list[dict]:
    return [c for c in open_cases(limit=10_000) if c["escalationRisk"] >= EARLY_WARNING_RISK or (c["overdue"] and c["severity"] != "Medium")]


def _top_terms(texts: list[str], k: int = 5) -> list[str]:
    if len(texts) < 2:
        return []
    vec = TfidfVectorizer(stop_words=STOP, ngram_range=(1, 2), min_df=1, sublinear_tf=True)
    try:
        m = vec.fit_transform(texts)
    except ValueError:
        return []
    weights = m.sum(axis=0).A1
    terms = vec.get_feature_names_out()
    return [terms[i] for i in weights.argsort()[::-1][:k]]


def clusters() -> list[dict]:
    """Recurring root causes: volume, open cases, trend, hotspots and characteristic words. Largest first."""
    df = load_cases()
    out = []
    for topic, g in df.groupby("topic"):
        months = g.dropna(subset=["date"]).groupby(g["date"].dt.strftime("%Y-%m")).size().sort_index()
        trend = None
        if len(months) >= 2 and months.iloc[-2] > 0:
            trend = round(100 * (months.iloc[-1] - months.iloc[-2]) / months.iloc[-2])
        is_open = g["status"].str.lower().isin(OPEN_STATUSES)
        out.append(dict(
            topic=topic, cases=int(len(g)), open=int(is_open.sum()), share=round(100 * len(g) / len(df)),
            unresolvedPct=round(100 * is_open.mean()), byMonth={k: int(v) for k, v in months.items()}, trendPct=trend,
            hotspots=[dict(state=s, cases=int(n)) for s, n in Counter(g["state"][g["state"] != ""]).most_common(3)],
            keywords=_top_terms(g["text"].tolist()), example=g["text"].iloc[0],
        ))
    return sorted(out, key=lambda c: -c["cases"])


def discover(k: int = 6) -> list[dict]:
    """Unsupervised cross-check: k-means on TF-IDF of the complaint texts. Shows what the data groups by itself."""
    df = load_cases()
    k = max(2, min(k, len(df) // 5))
    if len(df) < 10:
        return []
    vec = TfidfVectorizer(stop_words=STOP, ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    try:
        X = vec.fit_transform(df["text"])
    except ValueError:
        return []
    labels = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(X)
    terms = vec.get_feature_names_out()
    out = []
    for c in range(k):
        idx = (labels == c).nonzero()[0]
        centroid = X[idx].mean(axis=0).A1
        agree = Counter(df["topic"].iloc[idx]).most_common(1)[0]
        out.append(dict(cluster=c, cases=int(len(idx)), keywords=[terms[i] for i in centroid.argsort()[::-1][:5]],
                        closestTopic=agree[0], agreementPct=round(100 * agree[1] / len(idx))))
    return sorted(out, key=lambda c: -c["cases"])


def summary() -> dict:
    cases = open_cases(limit=10_000)
    return dict(open=len(cases), critical=sum(c["severity"] == "Critical" for c in cases),
                avgRisk=round(sum(c["escalationRisk"] for c in cases) / len(cases)) if cases else 0,
                overdue=sum(c["overdue"] for c in cases), source=load_cases()["source"].iloc[0])


if __name__ == "__main__":   # python complaints.py : the distribution to tune the thresholds on the real file
    cases = open_cases(limit=10_000)
    print(summary())
    print("severity:", Counter(c["severity"] for c in cases))
    print("risk percentiles:", pd.Series([c["escalationRisk"] for c in cases]).describe(percentiles=[.5, .75, .9, .95]).round(1).to_dict())
    print("early warnings:", len(early_warnings()))
    print("topics:", Counter(load_cases()["topic"]))
    for c in cases[:8]:
        print(c["id"], c["severity"], c["escalationRisk"], c["cluster"], "|", c["summary"][:70], c["reasons"])
