"""The complaint agent's brain: read a complaint, find its root cause, say how serious it is, how likely it is to escalate, and what to do first.

Nothing here is learned from data and no language model is used. Like the sales and quality agents, every number is a sum of named, signed,
worded factors, so the screen can answer "why is this critical?" and "why is the risk 87?":
  severity (how much is at stake): money, legal or public exposure, customers affected, the customer's value, repeat contacts
  escalation risk (how likely it is to escalate): threats, the risk of losing the customer, the deadline, repeat contacts, tone, who owns it
The root cause (cluster) comes from phrase patterns on the customer's words. Deadlines come from a policy table by level. All figures, customers and
policies are invented.
"""
import datetime as dt
import json
import re
from pathlib import Path

import advisor
from sales_agent import engine as sales

_K = Path(__file__).resolve().parents[1] / "knowledge"
POLICY = json.loads((_K / "complaints.json").read_text(encoding="utf-8"))
LEVELS = POLICY["levels"]                                   # Critical, High, Medium, Low, from the highest minimum score down
ORDER = list(LEVELS)                                        # most serious first
CLUSTERS = {k: dict(v, rx=re.compile(v["rx"], re.I)) for k, v in POLICY["clusters"].items()}
SIGNALS = {k: re.compile(v, re.I) for k, v in POLICY["signals"].items()}
RESOLUTIONS = POLICY["resolutions"]
FOLLOW_UP_HOURS = POLICY["follow_up_hours"]
REFUND_LIMIT = advisor.REFUND_LIMIT_TND

AMOUNT = re.compile(r"(?:[$€£]\s?(\d[\d,.]*))|(?:\b(\d[\d,.]*)\s?(?:tnd|dt|dinars?|dollars?|euros?|usd|eur)\b)", re.I)
FILE_MOOD = {"Angry": 5, "Frustrated": 5}


def level_of(score: int) -> str:
    return next(name for name, v in LEVELS.items() if score >= v["min"])


def sla_hours(level: str) -> int:
    return LEVELS[level]["sla_hours"]


def parse_amount(text: str) -> float | None:
    """The biggest amount of money the customer mentions (invented currency, treated as TND): "180 dinars", "$2,000", "45.5 TND"."""
    best = None
    for m in AMOUNT.finditer(text):
        raw = (m.group(1) or m.group(2)).rstrip(".,")
        raw = re.sub(r",(?=\d{3}\b)", "", raw).replace(",", ".")
        try:
            value = float(raw)
        except ValueError:
            continue
        best = value if best is None else max(best, value)
    return best


def classify(text: str) -> tuple[str, list[str]]:
    """The root-cause cluster with the most pattern hits (the first one on a tie), and the other clusters that also matched."""
    hits = {k: len(c["rx"].findall(text)) for k, c in CLUSTERS.items()}
    ranked = sorted((k for k, n in hits.items() if n), key=lambda k: -hits[k])
    return (ranked[0], ranked[1:]) if ranked else ("other", [])


def cluster_info(key: str) -> dict:
    if key == "other":
        return dict(label="Other", cause="Unknown", team="Care", action="Read the case, find the root cause and give the customer one owner.", resolutions=["explained"])
    return CLUSTERS[key]


def quote(rx: re.Pattern, text: str) -> str | None:
    m = rx.search(text)
    return m.group(0) if m else None


def short(text: str, n: int = 90) -> str:
    one = " ".join(text.split())
    first = re.split(r"(?<=[.!?])\s", one, maxsplit=1)[0]
    return first if len(first) <= n else first[: n - 1].rstrip() + "…"


def contacts_of(case: dict, others: list[dict], now: dt.datetime) -> int:
    """How many times this customer already contacted us about a problem: their other cases in the last 30 days, and the customer's own words about it."""
    since = now - dt.timedelta(days=30)
    prior = sum(1 for o in others if o["id"] != case["id"] and case["customer"] and o["customer"] == case["customer"] and o["opened_at"] >= since and o["opened_at"] <= case["opened_at"])
    return max(prior, 2 if SIGNALS["repeat"].search(case["text"]) else 0)       # "for the third time" counts as at least two earlier contacts


def severity(case: dict, customer: dict | None, contacts: int) -> dict:
    """How much is at stake, 0 to 100: money, legal or public exposure, customers affected, the customer's value, repeat contacts."""
    text = case["text"]
    factors = []

    def add(name, points, why):
        if points:
            factors.append(dict(name=name, points=points, why=why))

    amount = parse_amount(text)
    if amount is not None:
        add("Money at stake", 25 if amount >= 300 else 15 if amount >= 100 else 8 if amount >= 30 else 0, f"about {amount:g} TND is disputed")
    legal = quote(SIGNALS["legal"], text)
    add("Legal exposure", 30 if legal else 0, f"“{legal}”")
    public = quote(SIGNALS["public"], text)
    add("Public exposure", 12 if public and not legal else 0, f"“{public}”")
    affected = quote(SIGNALS["affected"], text)
    add("Customers affected", 10 if affected else 0, f"“{affected}”")
    profile = sales.PROFILES.get(customer["id"], {}) if customer else {}
    value, why = 0, []
    if (profile.get("tenureYears") or 0) >= 5:
        value, why = value + 8, why + [f"{profile['tenureYears']:g} years with us"]
    if customer and "Premium" in customer["contract"]:
        value, why = value + 8, why + ["premium plan"]
    if (profile.get("monthlyTnd") or 0) >= 100:
        value, why = value + 6, why + [f"{profile['monthlyTnd']} TND a month"]
    add("Customer value", min(15, value), ", ".join(why))
    add("Repeat contact", 16 if contacts >= 2 else 8 if contacts == 1 else 0, f"already {contacts} earlier contact{'s' if contacts != 1 else ''} about problems")
    score = max(0, min(100, sum(f["points"] for f in factors)))
    return dict(score=score, level=level_of(score), factors=factors)


def deadline(level: str, opened_at: dt.datetime, now: dt.datetime, sla: int | None = None) -> dict:
    """The time the case must be answered in, from the policy of its level."""
    total = sla or sla_hours(level)
    age = max(0.0, (now - opened_at).total_seconds() / 3600)
    return dict(slaHours=total, ageHours=round(age, 1), hoursLeft=round(total - age, 1), used=round(age / total, 2), overdue=age > total)


def escalation_risk(case: dict, customer: dict | None, sev: dict, contacts: int, due: dict) -> dict:
    """How likely the case is to escalate (to a supervisor, a regulator, the public, or the customer leaving), 0 to 100."""
    text = case["text"]
    factors = [dict(name="Starting point", points=10, why="every complaint can escalate")]

    def add(name, points, why):
        if points:
            factors.append(dict(name=name, points=points, why=why))

    legal, public = quote(SIGNALS["legal"], text), quote(SIGNALS["public"], text)
    if legal:
        add("Threatens to escalate", 25, f"legal or regulator: “{legal}”")
    elif public:
        add("Threatens to escalate", 15, f"going public: “{public}”")
    needs = sales.merge_needs(sales.conversation_needs([dict(speaker="customer", text=text)]), sales.file_needs(customer))
    mood = sales.mood_of([dict(speaker="customer", text=text)], customer)
    churn = sales.churn_risk(customer, needs, mood)
    add("Risk of losing the customer", min(20, round(0.2 * churn["score"])), f"churn risk {churn['score']} ({churn['level'].lower()})")
    used = due["used"]
    if used >= 1:
        add("Time pressure", 25, f"past its deadline by {abs(due['hoursLeft']):g} h")
    elif used >= 0.75:
        add("Time pressure", 15, f"{round(used * 100)}% of the {due['slaHours']} h deadline is used")
    elif used >= 0.5:
        add("Time pressure", 8, f"{round(used * 100)}% of the {due['slaHours']} h deadline is used")
    add("Repeat contacts", min(18, 6 * contacts), f"{contacts} earlier contact{'s' if contacts != 1 else ''}")
    tone = quote(SIGNALS["tone"], text)
    file_mood = FILE_MOOD.get(customer["mood"], 0) if customer else 0
    if tone:
        add("Tone", 10, f"“{tone}”")
    elif file_mood:
        add("Tone", file_mood, f"the customer file says {customer['mood'].lower()}")
    if customer and customer["transfers"] >= 2:
        add("Passed around", 8, f"transferred {customer['transfers']} times before")
    if SIGNALS["affected"].search(text):
        add("Customers affected", 5, "more than one customer suffers from this")
    if case["status"] == "open" and due["used"] > 0.25:
        add("Nobody owns it", 8, "still not taken after a quarter of the deadline")
    if case["status"] == "taken":
        add("Someone is on it", -8, f"taken by {case.get('assigned') or 'an agent'}")
    score = max(0, min(100, sum(f["points"] for f in factors)))
    return dict(score=score, factors=factors, churn=churn["score"])


def warning(case: dict, risk: dict, due: dict) -> dict | None:
    """The early warning: a case a supervisor should know about now."""
    if case["status"] in ("resolved", "closed"):
        return None
    why = []
    if risk["score"] >= 80:
        why.append(f"escalation risk {risk['score']}")
    if due["overdue"]:
        why.append(f"{abs(due['hoursLeft']):g} h past its deadline")
    elif due["hoursLeft"] <= 2 and risk["score"] >= 60:
        why.append(f"only {max(due['hoursLeft'], 0):g} h left with a risk of {risk['score']}")
    if not why:
        return None
    return dict(why="; ".join(why), hoursLeft=due["hoursLeft"], alerted=case.get("alerted", False))


def next_actions(case: dict, cluster: dict, amount: float | None, contacts: int, risk: dict, due: dict) -> list[dict]:
    """What to do first, each action with the reason it is there."""
    text, out = case["text"], []
    out.append(dict(action=cluster["action"], why=f"the usual first step for “{cluster['label'].lower()}”", who=cluster["team"]))
    if amount is not None and amount > REFUND_LIMIT and any(k in cluster["label"].lower() for k in ("billing", "roaming", "bill")):
        out.append(dict(action="Get a supervisor's approval before any refund.", why=f"about {amount:g} TND is above the {REFUND_LIMIT} TND limit", who="Supervisor"))
    if SIGNALS["legal"].search(text):
        out.append(dict(action="Involve compliance before replying.", why="the customer mentions legal action or a regulator", who="Compliance"))
    elif SIGNALS["public"].search(text):
        out.append(dict(action="Reply within 2 hours and offer a call back.", why="the customer may post about it publicly", who="Care"))
    if contacts >= 1:
        out.append(dict(action="Give the case one owner and do not transfer it again.", why=f"{contacts} earlier contact{'s' if contacts != 1 else ''} already", who="Care"))
    if due["overdue"]:
        out.append(dict(action="Apologise for the delay when you call.", why=f"the deadline passed {abs(due['hoursLeft']):g} h ago", who="Care"))
    if risk["score"] >= 80 and not case.get("alerted"):
        out.append(dict(action="Alert a supervisor now.", why=f"escalation risk {risk['score']}", who="Supervisor"))
    out.append(dict(action=f"Confirm the fix in writing, then call back after {FOLLOW_UP_HOURS} h to check the customer trusts us again.", why="a complaint is closed when the customer is satisfied, not when it is answered", who="Care"))
    return out


def analyse(case: dict, others: list[dict], now: dt.datetime) -> dict:
    """Everything the agent says about one case. `case` is a row of the store, `others` the other cases (to count repeat contacts)."""
    customer = advisor.get_customer(case["customer"]) if case.get("customer") else None
    key, extra = classify(case["text"])
    cluster = cluster_info(key)
    n = contacts_of(case, others, now)
    sev = severity(case, customer, n)
    level = case["override"] if case.get("override") in LEVELS else sev["level"]
    due = deadline(level, case["opened_at"], now, case.get("sla_hours") if not case.get("override") else None)
    risk = escalation_risk(case, customer, sev, n, due)
    amount = parse_amount(case["text"])
    return dict(
        id=case["id"], summary=case["summary"], severity=level, escalationRisk=risk["score"], cluster=cluster["label"], hoursLeft=due["hoursLeft"],
        clusterKey=key, otherClusters=[cluster_info(k)["label"] for k in extra], cause=cluster["cause"], team=cluster["team"],
        customerId=case.get("customer"), customer=customer["name"] if customer else None, status=case["status"], assigned=case.get("assigned"),
        channel=case.get("channel", "call"), source=case.get("source", "agent"), opened=case["opened_at"].isoformat(timespec="minutes"),
        severityScore=sev["score"], computedLevel=sev["level"], overridden=level != sev["level"], severityFactors=sev["factors"],
        riskFactors=risk["factors"], deadline=due, contacts=n, amount=amount, warning=warning(case, risk, due),
        actions=next_actions(case, cluster, amount, n, risk, due),
    )


def triage(text: str, customer_id: str | None, now: dt.datetime, others: list[dict] | None = None) -> dict:
    """Read a complaint that is not saved yet (a case as it would be if it were opened now)."""
    case = dict(id="NEW", customer=customer_id, text=text, summary=short(text), opened_at=now, status="open", assigned=None, override=None, channel="call", source="agent")
    return analyse(case, others or [], now)
